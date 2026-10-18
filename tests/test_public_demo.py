import asyncio
import hashlib
import json
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from premise.bootstrap import prepare_graph
from premise.config import Settings
from premise.public_demo import BANNER, DISABLED, PublicDemoDisabled, PublicDemoMiddleware
from premise.web.app import create_app
from conftest import SANDBOX, NOW


def snapshot(graph):
    facts = graph.read('MATCH (f:Fact) RETURN f.id AS id, f.value AS value ORDER BY id')
    return (graph.read('MATCH (n) RETURN count(n) AS n'),
            graph.read('MATCH ()-[r]->() RETURN count(r) AS n'),
            hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest())


def test_public_requests_are_read_only_and_keep_real_verdicts(new_graph, monkeypatch):
    graph = new_graph()
    config = Settings(public_demo=True, sandbox_dir=str(SANDBOX), github_token='', llm_provider='codex-cli')
    prepare_graph(graph, config)
    seeded = snapshot(graph)
    prepare_graph(graph, config)
    assert snapshot(graph) == seeded  # no duplicate records or re-ingestion on restart
    graph.write('MATCH (a:Assessment) REMOVE a.public_seed_ready')
    prepare_graph(graph, config)  # complete a seed interrupted before its final marker
    assert snapshot(graph) == seeded
    app = create_app(graph, config, graph_api_at_ms=NOW)
    with TestClient(app) as http:
        # The startup-only temporary projections are complete; requests may not create any.
        def forbidden(*a, **kw):
            pytest.fail('Public request attempted a write, repair search, model or GitHub action')
        monkeypatch.setattr(graph, 'write', forbidden)
        monkeypatch.setattr(graph, 'sibling', forbidden)
        monkeypatch.setattr('premise.agent.analyst.make_adapter', forbidden)
        monkeypatch.setattr('premise.reasoning.repair.Repairer.run', forbidden)
        before = snapshot(graph)
        graphs_before = graph.graph.client.execute_command('GRAPH.LIST')
        for path in ('/', '/explore', '/what-if', '/benchmark', '/continuity', '/entities/ADR-012', '/docs', '/redoc'):
            response = http.get(path)
            assert response.status_code == 200, (path, response.text)
            assert 'Public demo on FalkorDB Cloud. Read only.' in response.text
        for _ in range(3):
            response = http.post('/api/check', json={'changes': [{'fact': 'paylane.retry_window_hours', 'value': 72}]})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result['verdict'] == 'BLOCKED'
            assert len([g for g in result['not_holding'] if g['status'] == 'broken']) == 4
            assert result['verified_fixes'] == []
            result = http.post('/api/ask', json={'question': 'Why does ADR-012 exist?'}).json()
            assert result['mode'] == 'deterministic' and result['sources']
            assert 'ADR-012' in result['answer_markdown']
        assert http.post('/api/check', json={'changes': [{'fact': 'paylane.retry_window_hours', 'value': 72}], 'include_fixes': True}).status_code == 403
        assert http.post('/api/check', json={'files': {'config/paylane.yaml': 'retry_window_hours: 72'}, 'include_fixes': True}).status_code == 403
        for path in ('/healthz', '/api/health', '/api/graph/overview', '/api/graph/facts',
                     '/api/graph/timeline', '/api/graph/node/G_DEDUPE',
                     '/api/graph/neighborhood?focus=G_DEDUPE', '/api/graph/path?from=G_DEDUPE&to=ADR-012',
                     '/api/continuity?person=p_jun', '/api/benchmark', '/api/benchmark/questions'):
            response = http.get(path)
            assert response.status_code == 200, (path, response.text)
        from premise.github.store import Store
        for record in Store(graph).recent():
            assert http.get('/assessments/' + record['id']).status_code == 200
            assert http.get('/api/assessments/' + record['id']).status_code == 200
        assert snapshot(graph) == before
        assert graph.graph.client.execute_command('GRAPH.LIST') == graphs_before


def test_disabled_verbs_fail_before_graph_or_handler():
    config = Settings(public_demo=True)
    http = TestClient(create_app(Mock(), config))
    # These action routes are absent in v1; the boundary rejects them before dispatch.
    for method, path in [('POST', '/api/ingest'), ('POST', '/api/reload'), ('POST', '/api/steward'),
                         ('POST', '/api/fix'), ('POST', '/api/status'), ('POST', '/api/comment'),
                         ('DELETE', '/api/graph'), ('PUT', '/api/check'), ('PATCH', '/api/ask')]:
        response = http.request(method, path, json={})
        assert response.status_code == 403 and response.json()['detail'] == DISABLED
    assert TestClient(create_app(Mock(), Settings(public_demo=False, poll_enabled=False))).post('/api/ingest').status_code == 404


def test_model_and_pipeline_entry_points_are_disabled():
    from premise.agent.llm import make_adapter
    from premise.agent.fix_agent import augment_fixes
    from premise.github.poller import Pipeline
    config = Settings(public_demo=True)
    for call in (lambda: make_adapter(config), lambda: augment_fixes(None, None, config, Mock()),
                 lambda: Pipeline(None, None, None, config)):
        with pytest.raises(PublicDemoDisabled, match='Disabled in the public demo'):
            call()


@pytest.mark.parametrize('command', ['ingest', 'poll-once', 'reconcile', 'steward', 'demo', 'mcp', 'reset --demo', 'assess --pr 1 --execute', 'bench run'])
def test_public_cli_guards(command, monkeypatch, capsys):
    from premise.cli import main
    monkeypatch.setattr('premise.cli.settings', lambda: Settings(public_demo=True))
    assert main(command.split()) == 2
    assert DISABLED in capsys.readouterr().err


@pytest.mark.parametrize('command', ['run', 'reset', 'eval', 'load-knowledge', 'serve'])
def test_public_v2_cli_guards(command, monkeypatch, capsys):
    from premise_v2.cli import main
    monkeypatch.setattr('premise_v2.cli.settings', lambda: Settings(public_demo=True))
    assert main([command]) == 2
    assert DISABLED in capsys.readouterr().err


def test_v2_dismiss_disabled_before_staging_access():
    from premise_v2.web import create_app as create_v2
    staging, decision, knowledge = Mock(), Mock(), Mock()
    staging.c.graph_name, decision.graph_name, knowledge.graph_name = 'stage', 'decision', 'knowledge'
    app = create_v2(staging, decision, knowledge, SANDBOX, config=Settings(public_demo=True))
    response = TestClient(app).post('/item/test/dismiss', data={'csrf': 'fake'})
    assert response.status_code == 403 and response.json()['detail'] == DISABLED
    staging.reject.assert_not_called()


def test_limits_reset_without_trusting_forwarded_headers():
    app = FastAPI()
    app.post('/api/check')(lambda: {'ok': True})
    tick = [0]
    app.add_middleware(PublicDemoMiddleware, limit=2, body_limit=32, clock=lambda: tick[0])
    http = TestClient(app)
    assert http.post('/api/check', content=b'x' * 33).status_code == 413
    for ip in ('1.2.3.4', '5.6.7.8'):
        assert http.post('/api/check', headers={'X-Forwarded-For': ip}).status_code == 200
    response = http.post('/api/check', headers={'X-Forwarded-For': '9.9.9.9'})
    assert response.status_code == 429 and response.headers['Retry-After'] == '60'
    tick[0] = 61
    assert http.post('/api/check').status_code == 200


def test_chunked_size_cap_before_application():
    async def run():
        called = False
        async def application(*args):
            nonlocal called
            called = True
        chunks = iter([{'type': 'http.request', 'body': b'12345', 'more_body': True},
                       {'type': 'http.request', 'body': b'67890', 'more_body': False}])
        messages = []
        async def receive(): return next(chunks)
        async def send(message): messages.append(message)
        await PublicDemoMiddleware(application, body_limit=8)(
            {'type': 'http', 'method': 'POST', 'path': '/api/check', 'headers': [], 'client': ('local', 0)}, receive, send)
        assert messages[0]['status'] == 413 and not called
    asyncio.run(run())


def test_host_port_and_proxy_policy(monkeypatch):
    from premise import bootstrap
    run = Mock()
    monkeypatch.setenv('PORT', '10000')
    monkeypatch.setattr(bootstrap, 'settings', lambda: Settings(public_demo=True))
    monkeypatch.setattr(bootstrap, 'prepare_graph', Mock())
    monkeypatch.setattr(bootstrap, 'create_app', Mock())
    monkeypatch.setattr(bootstrap.uvicorn, 'run', run)
    bootstrap.main()
    assert run.call_args.kwargs == dict(host='0.0.0.0', port=10000, proxy_headers=False)


def test_request_context_rejects_writes_and_resets_after_response():
    from premise.graph.client import GraphClient
    from premise.public_demo import read_only_request
    graph = GraphClient()
    http = TestClient(create_app(graph, Settings(public_demo=True)))
    @http.app.get('/probe-write')
    def probe():
        graph.write('CREATE (:ShouldNeverExist)')
    @http.app.get('/probe-delete')
    def probe_delete():
        graph.delete_graph()
    for path in ('/probe-write', '/probe-delete'):
        response = http.get(path)
        assert response.status_code == 403 and response.json()['detail'] == DISABLED
    assert graph._g is None  # no connection was needed to reject the operation
    assert not read_only_request.get()
