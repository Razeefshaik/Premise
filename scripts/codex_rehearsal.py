"""Explicit real Codex + real FalkorDB rehearsal, isolated from GitHub and the live graph.

Run: .venv/Scripts/python.exe scripts/codex_rehearsal.py --execute
Consumes the signed-in Codex account's model allowance. Never creates/merges a PR.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import time
import uuid

from fastapi.testclient import TestClient

from premise.agent.codex_cli import CodexAdapter, resolve_binary
from premise.agent import analyst
from premise.agent.fix_agent import FixSession, SCHEMAS
from premise.config import settings
from premise.graph.client import GraphClient
from premise.ingest.run import ingest
from premise.scenarios import load_scenarios, run_scenario, scenario_now
from premise.web.app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--output', default='artifacts/codex-rehearsal.json')
    args = parser.parse_args()
    config = replace(settings(), llm_provider='codex-cli', poll_enabled=False, auto_fix_pr=False,
                     graph_name='premise_codex_rehearsal_' + uuid.uuid4().hex[:10])
    graph = GraphClient(config.falkordb_host, config.falkordb_port, config.graph_name)
    binary = resolve_binary(config.codex_binary)
    version = subprocess.check_output([binary, '--version'], text=True).strip()
    report = {'provider': 'codex-cli', 'cli_version': version, 'requested_model': config.codex_model or 'CLI default',
              'graph': config.graph_name, 'github_writes': False, 'questions': []}
    started = time.monotonic()
    adapters = []
    original_factory = analyst.make_adapter
    def recording_factory(settings, client):
        adapter = CodexAdapter(settings.codex_binary, settings.codex_model, client, settings.codex_timeout_seconds)
        adapters.append(adapter)
        return adapter
    try:
        ingest(graph, config.sandbox_dir, 'codex-rehearsal')
        analyst.make_adapter = recording_factory
        with TestClient(create_app(graph, config)) as client:
            for question in (
                'Which guarantees are load bearing, and which rest on unverified assumptions?',
                'Why does ADR-012 skip idempotency, and who should review it now?',
                'Who knows paymentservice, and what evidence supports that?',
            ):
                before = time.monotonic()
                response = client.post('/api/ask', json={'question': question})
                response.raise_for_status()
                answer = response.json()
                item = {'question': question, 'mode': answer['mode'], 'provider': answer['provider'],
                        'answer': answer['answer_markdown'], 'source_count': len(answer['sources']),
                        'tools': [row['tool'] for row in answer['tool_results']],
                        'provider_error': answer['provider_error'], 'seconds': round(time.monotonic()-before, 2),
                        'trace': adapters[-1].trace, 'candidate': adapters[-1].last_answer}
                report['questions'].append(item)
                print(json.dumps(item), flush=True)
                assert answer['sources'] and answer['tool_results']
        data = load_scenarios('scenarios/scenarios.yaml')
        result = run_scenario(graph, Path(config.sandbox_dir), data['scenarios']['S1'], scenario_now(data))
        session = FixSession(graph, result)
        adapter = CodexAdapter(config.codex_binary, config.codex_model, graph, config.codex_timeout_seconds)
        calls = []
        def dispatch(name, arguments):
            value = session.dispatch(name, arguments)
            calls.append({'tool': name, 'arguments': arguments,
                          'all_hold': value.get('all_hold') if isinstance(value, dict) else None})
            return value
        answer = adapter.tool_loop(
            'Find a complete numeric remedy. Call violation_context, then test_fix for every candidate. '
            'Only controllable facts, at most three. Never revert a PR or change external facts. '
            'Return JSON {fixes:[{changes,rationale}]}. Return only fixes you actually tested.',
            json.dumps({'assessment': result.model_dump(exclude={'fixes', 'fix_budget_used'})}, default=str), SCHEMAS, dispatch, budget=8)
        fixes = session.accept(answer)
        report['repair'] = {'verdict': result.verdict, 'tool_calls': calls, 'trace': adapter.trace,
                            'accepted_fixes': [fix.model_dump() for fix in fixes]}
        assert any(fix.status == 'verified' and fix.origin == 'llm' for fix in fixes), 'No live Codex fix passed graph verification'
        assert any(row['tool'] == 'test_fix' and row['all_hold'] is True for row in calls)
        report['success'] = all(item['mode'] == 'llm' and item['provider'] == 'codex-cli' for item in report['questions'])
        print(json.dumps(report['repair']), flush=True)
        assert report['success'], 'A model answer fell back; inspect the rehearsal record'
    finally:
        analyst.make_adapter = original_factory
        report['seconds'] = round(time.monotonic()-started, 2)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        graph.delete_graph()
        print(f'Rehearsal record: {output}', flush=True)


if __name__ == '__main__':
    main()
