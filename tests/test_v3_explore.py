from dataclasses import replace
from fastapi.testclient import TestClient
from premise.config import Settings
from premise.web.app import create_app


def test_explorer_page_and_pinned_local_library(kestrel):
    with TestClient(create_app(kestrel, replace(Settings(), poll_enabled=False, llm_provider='none'))) as http:
        response = http.get('/explore')
        assert response.status_code == 200 and 'explorer-canvas' in response.text
        assert 'cytoscape-3.30.4.min.js' in response.text
        assert http.get('/static/vendor/cytoscape-3.30.4.min.js').status_code == 200
        assert '/explore' in http.get('/').text


def test_consequences_expose_touched_and_real_read_queries(kestrel):
    with TestClient(create_app(kestrel, replace(Settings(), poll_enabled=False, llm_provider='none'))) as http:
        data = http.post('/api/check', json={'changes':[{'fact':'paylane.retry_window_hours','value':72}]}).json()
        assert data['touched'] == ['A_RETRY_WINDOW']
        assert data['verdict'] == 'BLOCKED' and len(data['not_holding']) == 4
        assert next(g for g in data['guarantees'] if g['id']=='G_DEDUPE')['status']=='broken'
        assert next(a for a in data['assumptions'] if a['id']=='A_RETRY_WINDOW')['state']=='violated'
        assert data['queries'] and all(q['operation'] == 'read' for q in data['queries'])
        facts = http.get('/api/graph/facts').json()
        assert facts['facts'] and facts['presets'] and facts['queries']


def test_explorer_names_and_hypothetical_recovery(kestrel):
    with TestClient(create_app(kestrel, replace(Settings(), poll_enabled=False, llm_provider='none'))) as http:
        node = http.get('/api/graph/node/G_DEDUPE').json()
        assert node['health']=='holds' and node['names']['p_jun']=='Jun Park'
        assert all(person in node['names'] for person in node['reviewers'])
        repaired = http.post('/api/check', json={'changes':[
            {'fact':'paylane.retry_window_hours','value':72},
            {'fact':'webhook.dedupe_ttl_hours','value':72},
            {'fact':'redis.max_ttl_hours','value':72}]}).json()
        assert repaired['verdict']=='CLEAR_WITHIN_SCOPE'
        assert all(g['status']=='holds' for g in repaired['guarantees'])
        assert next(a for a in repaired['assumptions'] if a['id']=='A_RETRY_WINDOW')['state']=='holding'
        # The overlay must never change baseline graph health.
        assert http.get('/api/graph/node/G_DEDUPE').json()['health']=='holds'
