import re
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from premise.cli import main
from premise.config import Settings
from premise.graph.client import GraphUnavailable
from premise.graph.tools import GraphTools
from premise.web.app import create_app
from conftest import SANDBOX, NOW

S1=[{'fact':'paylane.retry_window_hours','value':72}]
FIX=[{'fact':'webhook.dedupe_ttl_hours','value':72},{'fact':'redis.max_ttl_hours','value':72}]
BROKEN={'G_DEDUPE','G_CHARGE_ONCE','G_LEDGER_CONSISTENT','G_REFUND_MATCH'}


def snapshot(c):
    return (c.read('MATCH (n) RETURN count(n) AS n'), c.read('MATCH ()-[r]->() RETURN count(r) AS n'),
            c.read('MATCH (s:GraphState) RETURN properties(s) AS state'))


def test_preflight_same_reasoning_and_verified_fix(kestrel):
    tools=GraphTools(kestrel,NOW)
    r=tools.call('check_change',{'changes':S1})
    assert r['hypothetical'] and not r['stored'] and r['verdict']=='BLOCKED'
    assert {g['id'] for g in r['not_holding']}==BROKEN
    assert {'changes':{x['fact']:x['value'] for x in FIX}} in r['verified_fixes']
    assert tools.call('check_change',{'changes':S1+FIX})['verdict']=='CLEAR_WITHIN_SCOPE'
    assert tools.call('check_change',{'changes':S1,'include_fixes':False})['verified_fixes']==[]
    assert r['decisions'] and any('p_jun' in d['reviewers'] for d in r['decisions'])


def test_unknown_and_bad_types_need_review(kestrel):
    tools=GraphTools(kestrel,NOW)
    r=tools.call('check_change',{'changes':[{'fact':'webhook.dedupe_ttl_hours','value':'24h'}]})
    assert r['verdict']=='NEEDS_REVIEW' and 'R_UNKNOWN' in {x['code'] for x in r['reasons']}
    for values in ([{'fact':'foo.bar','value':1}], [{'fact':'foo.bar','value':1},{'fact':'emailservice.retry_max_attempts','value':8}]):
        r=tools.call('check_change',{'changes':values})
        assert r['verdict']=='NEEDS_REVIEW' and not r['verified_fixes']
        assert r['reasons'][0]['code']=='R_UNTRACKED'


def test_files_equivalent_malformed_deletion_and_model_edit(kestrel):
    tools=GraphTools(kestrel,NOW)
    text=(SANDBOX/'config/partners/paylane.yaml').read_text().replace('window_hours: 24','window_hours: 72')
    a=tools.call('check_change',{'changes':S1})
    b=tools.call('check_files',{'files':{'config/partners/paylane.yaml':text}})
    for key in ('verdict','not_holding','verified_fixes'):
        assert a[key]==b[key]
    r=tools.call('check_files',{'files':{'config/webhookingress.yaml':'x: [oops'}})
    assert r['verdict']=='NEEDS_REVIEW' and r['reasons'][0]['code']=='R_UNPARSEABLE'
    r=tools.call('check_change',{'changes':[{'file':'config/webhookingress.yaml','key':'dedupe.ttl_hours','delete':True}]})
    assert r['verdict']=='NEEDS_REVIEW' and r['changed'][0]['new'] is None
    assert tools.call('check_files',{'files':{'adr/ADR-007.md':'edited'}})['verdict']=='NEEDS_REVIEW'


def test_preflight_never_writes(kestrel,monkeypatch):
    before=snapshot(kestrel)
    original=kestrel.read
    def read(query,params=None):
        assert not re.search(r'\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP)\b',query,re.I)
        return original(query,params)
    monkeypatch.setattr(kestrel,'read',read)
    monkeypatch.setattr(kestrel,'write',lambda *args,**kwargs:pytest.fail('preflight attempted a write'))
    for _ in range(5):
        GraphTools(kestrel,NOW).call('check_change',{'changes':S1})
    assert snapshot(kestrel)==before


def test_not_ready_guard(new_graph):
    with pytest.raises(GraphUnavailable):
        GraphTools(new_graph()).call('check_change',{'changes':S1})


@pytest.mark.parametrize('args',[
    {'changes':[]}, {'changes':S1*21}, {'changes':S1,'extra':True},
    {'changes':[{'fact':'x','value':None}]}, {'changes':[{'fact':'x','value':float('nan')}]},
    {'changes':[{'fact':'x','value':1,'delete':True}]}, {'changes':[{'fact':'x','delete':False}]},
    {'changes':[{'fact':'x','value':{}}]}, {'changes':[{'file':'../x','key':'x','value':1}]},
])
def test_change_validation(kestrel,args):
    with pytest.raises(ValueError): GraphTools(kestrel,NOW).call('check_change',args)


@pytest.mark.parametrize('files',[
    {}, {f'x{i}':'x' for i in range(11)}, {'../x':'x'}, {'/x':'x'}, {'C:/x':'x'},
    {'x\\y':'x'}, {'x':'x'*200001}, {'x':'é'*100001},
])
def test_file_validation(kestrel,files):
    with pytest.raises(ValueError): GraphTools(kestrel,NOW).call('check_files',{'files':files})


@pytest.mark.parametrize('sets,expected',[
    (['paylane.retry_window_hours=72'],2),
    (['webhook.dedupe_ttl_hours=24h'],1),
    (['paylane.retry_window_hours=72','webhook.dedupe_ttl_hours=72','redis.max_ttl_hours=72'],0),
])
def test_cli_exit_codes(kestrel,capsys,sets,expected):
    argv=['--graph',kestrel.graph_name,'--host',kestrel.host,'--port',str(kestrel.port),'check','--json']
    for value in sets: argv+=['--set',value]
    assert main(argv)==expected
    assert 'hypothetical' in capsys.readouterr().out


def test_http_check_validation_and_no_writes(kestrel):
    before=snapshot(kestrel)
    with TestClient(create_app(kestrel,replace(Settings(),poll_enabled=False))) as client:
        assert client.post('/api/check',json={'changes':S1}).json()['verdict']=='BLOCKED'
        assert client.post('/api/check',json={'changes':[{'fact':'foo.bar','value':1}]}).status_code==422
        assert client.post('/api/check',json={'files':{'../secret':'x'}}).status_code==422
        assert client.post('/api/check',json={'changes':S1,'files':{}}).status_code==422
    assert before==snapshot(kestrel)
