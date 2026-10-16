from fastapi.testclient import TestClient
from premise.config import Settings
from premise.web.app import create_app
from premise.scenarios import run_scenario
from conftest import SANDBOX,SCENARIOS,NOW


def test_departures_native_algorithms_and_source_isolation(kestrel):
    before=kestrel.read('MATCH (n) RETURN count(n) AS n')
    with TestClient(create_app(kestrel,Settings(poll_enabled=False,llm_provider='none'),graph_api_at_ms=NOW)) as http:
        r=http.get('/api/continuity',params={'person':'p_anika'})
        assert r.status_code==200,r.text
        data=r.json()
        assert 'A_STABLE_EVENT_ID' in [a['id'] for a in data['unverified_assumptions']]
        assert next(g for g in data['changed_guarantees'] if g['id']=='G_DEDUPE')['status']=='unknown'
        assert 'ADR-007' in data['affected_decisions']
        assert data['bridge']['score']>=0 and data['bridge']['rank']>=1
        assert any('algo.betweenness' in q['cypher'] for q in data['queries'])
        assert any('algo.WCC' in q['cypher'] for q in data['queries'])
        assert all(q['operation']=='read' for q in data['queries'] if q.get('graph') is None)
        assert data['projection']['namespace'] not in kestrel.graph.client.execute_command('GRAPH.LIST')
        jun=http.get('/api/continuity',params={'person':'p_jun'}).json()
        route=next(d for d in jun['reviewer_routing'] if d['id']=='ADR-012')
        assert 'p_jun' in route['before'] and 'p_jun' not in route['after'] and route['after']
        assert http.get('/api/continuity?person=absent').status_code==404
    assert before==kestrel.read('MATCH (n) RETURN count(n) AS n')


def test_empty_departure_keeps_all_twelve_scenarios_identical(kestrel,monkeypatch):
    scenarios=SCENARIOS['scenarios']
    before={k:run_scenario(kestrel,SANDBOX,v,NOW).model_dump() for k,v in scenarios.items()}
    original=kestrel.named
    def explicit_empty(name,params=None):
        if name in {'evaluate_assumptions','route_decision'}:params={**(params or {}),'gone':[]}
        return original(name,params)
    monkeypatch.setattr(kestrel,'named',explicit_empty)
    after={k:run_scenario(kestrel,SANDBOX,v,NOW).model_dump() for k,v in scenarios.items()}
    assert len(before)==12 and before==after
