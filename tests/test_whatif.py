from dataclasses import replace
from fastapi.testclient import TestClient
from premise.config import Settings
from premise.web.app import create_app
from test_check_change import S1, FIX, snapshot


def test_whatif_facts_and_server_rendering(kestrel):
    with TestClient(create_app(kestrel,replace(Settings(),poll_enabled=False))) as client:
        page=client.get('/what-if')
        assert page.status_code==200
        assert page.text.count('class="fact-input"')==12
        assert 'Hypothetical. Nothing is stored or posted.' in page.text
        assert 't_payments' in page.text and 'external' in page.text
        for preset in ('S1','S1_FIXED','S6','S12'): assert f'data-preset="{preset}"' in page.text


def test_whatif_api_and_read_only_proof(kestrel):
    before=snapshot(kestrel)
    with TestClient(create_app(kestrel,replace(Settings(),poll_enabled=False))) as client:
        for i in range(10):
            result=client.post('/api/check',json={'changes':S1+(FIX if i%2 else [])})
            assert result.status_code==200
            body=result.json()
            assert body['verdict']==('CLEAR_WITHIN_SCOPE' if i%2 else 'BLOCKED')
            assert len(body['not_holding'])==(0 if i%2 else 4)
            if not i%2: assert 'G_DEDUPE' in body['mermaid'] and body['names']['p_jun']=='Jun Park'
            assert ('class clear holds' if i%2 else 'G_DEDUPE') in body['mermaid']
        for payload in ({'changes':[{'fact':'unknown.fact','value':1}]},{'changes':'bad'},{'files':{'/etc/passwd':'x'}}):
            response=client.post('/api/check',json=payload)
            assert response.status_code==422 and 'Traceback' not in response.text
    assert snapshot(kestrel)==before
