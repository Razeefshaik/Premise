"""Smoke a running public app; optionally prove DB immutability with operator credentials.

Credentials come only from the invoking environment. Never print connection options.
"""
import argparse
import hashlib
import json
import os

import httpx

from premise.config import settings
from premise.graph.client import GraphClient
from premise.public_demo import DISABLED


def snapshot(graph):
    facts = graph.read('MATCH (f:Fact) RETURN f.id AS id,f.value AS value ORDER BY id')
    return {'nodes': graph.read('MATCH (n) RETURN count(n) AS n')[0]['n'],
            'edges': graph.read('MATCH ()-[r]->() RETURN count(r) AS n')[0]['n'],
            'facts_sha256': hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=os.getenv('PREMISE_BASE_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--verify-database', action='store_true', help='Compare the configured graph before/after')
    args = parser.parse_args()
    graph = GraphClient.from_settings(settings()) if args.verify_database else None
    before = snapshot(graph) if graph else None
    checked = []
    with httpx.Client(base_url=args.base_url.rstrip('/'), timeout=90) as http:
        for path in ('/', '/explore', '/what-if', '/benchmark', '/continuity', '/entities/ADR-012', '/docs', '/redoc'):
            r = http.get(path)
            assert r.status_code == 200, (path, r.status_code)
            assert 'Public demo on FalkorDB Cloud. Read only.' in r.text, path
            checked.append(path)
        for path in ('/healthz', '/api/health', '/api/graph/overview', '/api/graph/facts',
                     '/api/graph/timeline', '/api/graph/overview?at=2027-03-02',
                     '/api/graph/node/G_DEDUPE', '/api/graph/neighborhood?focus=G_DEDUPE&depth=2',
                     '/api/graph/path?from=G_DEDUPE&to=ADR-012', '/api/continuity?person=p_jun',
                     '/api/benchmark', '/api/benchmark/questions', '/openapi.json'):
            r = http.get(path)
            assert r.status_code == 200, (path, r.status_code)
            checked.append(path)
        for _ in range(3):
            r = http.post('/api/check', json={'changes': [{'fact': 'paylane.retry_window_hours', 'value': 72}]})
            assert r.status_code == 200, r.status_code
            result = r.json()
            assert result['verdict'] == 'BLOCKED', result['verdict']
            assert sum(g['status'] == 'broken' for g in result['not_holding']) == 4
            assert result['verified_fixes'] == []
            r = http.post('/api/ask', json={'question': 'Why does ADR-012 exist, and who reviews it?'})
            assert r.status_code == 200, r.status_code
            answer = r.json()
            assert answer['mode'] == 'deterministic' and answer['sources']
            assert 'ADR-012' in answer['answer_markdown']
        repair = http.post('/api/check', json={'changes': [{'fact': 'paylane.retry_window_hours', 'value': 72},
                    {'fact': 'webhook.dedupe_ttl_hours', 'value': 72}, {'fact': 'redis.max_ttl_hours', 'value': 72}]})
        assert repair.status_code == 200 and repair.json()['verdict'] == 'CLEAR_WITHIN_SCOPE'
        for path in ('/api/ingest', '/api/reload', '/api/steward', '/api/fix', '/api/status', '/api/comment'):
            r = http.post(path, json={})
            assert r.status_code == 403 and r.json()['detail'] == DISABLED
        r = http.post('/api/check', json={'changes': [{'fact': 'paylane.retry_window_hours', 'value': 72}], 'include_fixes': True})
        assert r.status_code == 403 and r.json()['detail'] == DISABLED
        if graph:
            from premise.github.store import Store
            for row in Store(graph).recent():
                for path in ('/assessments/' + row['id'], '/api/assessments/' + row['id']):
                    assert http.get(path).status_code == 200, path
                    checked.append(path)
    after = snapshot(graph) if graph else None
    assert before == after
    print(json.dumps({'result': 'PASS', 'checked': checked, 'paylane_72': 'BLOCKED; 4 guarantees broken',
                      'repair_preset': 'CLEAR_WITHIN_SCOPE', 'ask': 'deterministic; ADR-012 with sources',
                      'write_routes': '403', 'database_before': before, 'database_after': after,
                      'database_immutability': 'PASS' if graph else 'NOT CHECKED (use --verify-database)'}, indent=2))


if __name__ == '__main__':
    main()
