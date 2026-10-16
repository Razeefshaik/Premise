from fastapi.testclient import TestClient
from premise.config import Settings
from premise.web.app import create_app


def test_forecast_uses_existing_health_without_writes(kestrel,monkeypatch):
    before=kestrel.read('MATCH (n) RETURN count(n) AS n')
    def forbidden(*args,**kwargs):raise AssertionError('time machine wrote to graph')
    monkeypatch.setattr(kestrel,'write',forbidden)
    with TestClient(create_app(kestrel,Settings(poll_enabled=False,llm_provider='none'))) as http:
        current=http.get('/api/graph/overview?at=2026-10-16').json()
        future=http.get('/api/graph/overview?at=2027-03-02').json()
        status=lambda data,id:next(n['health'] for n in data['nodes'] if n['id']==id)
        assert status(current,'G_DEDUPE')=='holds'
        assert status(future,'G_DEDUPE')=='unknown'
        assert sum(n['label']=='Guarantee' and n['health']=='unknown' for n in future['nodes'])>=4
        assert current['queries'] and future['queries']
        for at in ('yesterday','2027-02-30','20270302'):
            response=http.get('/api/graph/overview',params={'at':at})
            assert response.status_code==422 and response.json()['queries']==[]
        timeline=http.get('/api/graph/timeline').json()
        assert any(m['date']=='2027-03-01' for m in timeline['marks'])
    assert before==kestrel.read('MATCH (n) RETURN count(n) AS n')
