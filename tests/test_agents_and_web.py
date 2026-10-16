import json
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from premise.agent.llm import request, Adapter
from premise.agent.fix_agent import FixSession, augment_fixes
from premise.agent.analyst import answer_question
from premise.agent.verify import verify_answer
from premise.config import Settings
from premise.graph.tools import GraphTools
from premise.github.store import Store
from premise.scenarios import run_scenario
from premise.web.app import create_app
from conftest import SANDBOX, SCENARIOS, NOW


def test_c3_no_sampling_prefill_or_forced_tool_choice():
    payload=request('claude-sonnet-5-5','system',[{'role':'user','content':'question'}],[{'name':'read'}])
    assert not {'temperature','top_p','top_k','tool_choice','thinking'} & payload.keys()
    assert payload['messages'][-1]['role']=='user'
    assert payload['output_config']=={'effort':'medium'}


def test_append_only_thinking_and_tool_budget():
    payloads=[]
    thinking={'type':'thinking','thinking':'reason','signature':'unchanged'}
    responses=[{'content':[thinking,{'type':'tool_use','id':'1','name':'read','input':{}}]},
               {'content':[{'type':'text','text':'{"fixes":[]}'}]}]
    class Messages:
        def create(self,**payload):
            # Capture immutable snapshots; the adapter appends later turns.
            payloads.append(json.loads(json.dumps(payload)));return responses.pop(0)
    adapter=Adapter('dummy','model',provider=SimpleNamespace(messages=Messages()))
    answer=adapter.tool_loop('system','question',[{'name':'read'}],lambda *_:{'id':'G_DEDUPE'},1)
    assert answer=={'fixes':[]}
    assert payloads[1]['messages'][1]['content'][0]==thinking
    assert len(payloads[1]['messages'])==3 and payloads[1]['messages'][0]==payloads[0]['messages'][0]


def test_fix_controller_drops_untested_and_false_fixes(kestrel):
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    session=FixSession(kestrel,result)
    good={'webhook.dedupe_ttl_hours':72,'redis.max_ttl_hours':72}
    bad={'webhook.dedupe_ttl_hours':72}
    assert session.accept({'fixes':[{'changes':good}]})==[]
    assert not session.dispatch('test_fix',{'changes':bad})['all_hold']
    assert not any(f.status=='verified' for f in session.accept({'fixes':[{'changes':bad}]}))
    assert session.dispatch('test_fix',{'changes':good})['all_hold']
    assert session.accept({'fixes':[{'changes':good}]})[0].status=='verified'
    for invalid in [{'paylane.retry_window_hours':24},{'unknown.fact':1},{'redis.max_ttl_hours':True},{'redis.max_ttl_hours':float('nan')}]:
        with pytest.raises(ValueError): session.dispatch('test_fix',{'changes':invalid})


def test_provider_failure_keeps_deterministic_fixes(kestrel):
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    before=[f.model_dump() for f in result.fixes]
    class Failed:
        def tool_loop(self,*args,**kwargs): raise RuntimeError('provider unavailable')
    augment_fixes(kestrel,result,Settings(),Failed())
    assert [f.model_dump() for f in result.fixes]==before


def test_fix_controller_rejects_reverting_controllable_pr_fact(kestrel):
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S2'],NOW)
    session=FixSession(kestrel,result)
    # This would be healthy, but it merely undoes the author's change from 5 to 8.
    with pytest.raises(ValueError,match='Reverts'):
        session.dispatch('test_fix',{'changes':{'emailservice.retry_max_attempts':5}})


def test_brain_health_and_routing(kestrel):
    tools=GraphTools(kestrel,NOW)
    health=tools.call('guarantee_health',{})
    rates=next(g for g in health['guarantees'] if g['id']=='G_RATES_FRESH')
    assert rates['status']=='unknown' and rates['unverified']==1
    assert health['guarantees'][0]['id']=='G_DEDUPE'
    lineage=tools.call('decision_lineage',{'id':'ADR-012'})
    assert lineage['reviewers'][0]=='p_jun' and lineage['sources']
    assert any('A_STABLE_EVENT_ID' in p['chain'] for p in lineage['paths'])
    owners=tools.call('who_knows',{'id':'paymentservice'})
    assert owners[0]['person']=='p_jun' and owners[0]['evidence']>=6
    with pytest.raises(ValueError): tools.call('write',{'query':'DELETE'})
    with pytest.raises(ValueError): tools.call('resolve',{'query':'x','cypher':'DELETE'})


def test_analyst_rejects_hallucinated_ids(kestrel):
    tools=GraphTools(kestrel,NOW)
    class Hallucinates:
        def tool_loop(self,system,question,schemas,dispatch,budget):
            dispatch('decision_lineage',{'id':'ADR-012'})
            return {'outcome':'answered_with_path','answer_markdown':'ADR-099 owns this','cited_ids':['ADR-099']}
    answer=answer_question(tools,'Why ADR-012?',adapter=Hallucinates())
    assert answer['mode']=='deterministic' and 'ADR-099' not in answer['answer_markdown']
    assert 'p_jun' in answer['answer_markdown']
    assert answer['sources']
    assert not verify_answer({'outcome':'answered_with_path','answer_markdown':'See https://evil.example','cited_ids':[]},[])
    # No dotted domain/id: this assertion specifically protects the URL ban.
    assert not verify_answer({'outcome':'answered_with_path','answer_markdown':'See https://localhost/','cited_ids':[]},[])
    invented={'outcome':'answered_with_path','answer_markdown':'ADR-099 owns this','cited_ids':['ADR-099']}
    assert not verify_answer(invented,[{'tool':'resolve','arguments':{'query':'ADR-099'},'rows':[]}])
    assert not verify_answer(invented,[{'tool':'decision_lineage','arguments':{'id':'ADR-099'},'rows':{'outcome':'unknown_entity','id':'ADR-099'}}])
    unknown=answer_question(tools,'zzzzfrobnitz')
    assert unknown['outcome']=='not_in_graph' and 'does not establish' in unknown['answer_markdown']
    assert answer_question(tools,'What about G_ABSENT?')['outcome']=='unknown_entity'
    assert answer_question(tools,'What about A_ABSENT?')['outcome']=='unknown_entity'


def test_web_brain_assessment_entities_and_failure(kestrel):
    config=replace(Settings(),poll_enabled=False)
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    result.pr='pr:101';result.head_sha='local-test'
    pr={'number':101,'title':'Local test','state':'open','head':{'sha':'local-test','ref':'s1','repo':{'full_name':'test/kestrel'}},'base':{'ref':'main','repo':{'full_name':'test/kestrel'}}}
    aid=Store(kestrel).save(result,pr)
    with TestClient(create_app(kestrel,config)) as client:
        assert client.get('/healthz').status_code==200
        brain=client.get('/')
        assert brain.status_code==200 and 'What still holds?' in brain.text
        assessment=client.get('/assessments/'+aid)
        assert assessment.status_code==200 and 'ADR-016' in assessment.text
        assert 'paylane | retry | window' in assessment.text
        assert 'Attested:' in assessment.text and 'Review by:' in assessment.text
        assert '1788307200000' not in assessment.text
        assert '"person":' not in assessment.text
        assert client.get('/api/assessments/'+aid).json()['verdict']=='BLOCKED'
        for id in ['ADR-012','G_DEDUPE','A_RETRY_WINDOW','paymentservice','p_jun']:
            assert client.get('/entities/'+id).status_code==200
        assert client.get('/entities/ADR-099').status_code==404
        assert client.post('/api/ask',json={'question':'Why ADR-012?'}).status_code==200
        assert client.post('/api/ask',json={'question':''}).status_code==422


@pytest.mark.asyncio
async def test_mcp_official_stdio_read_tools(kestrel,falkordb_port):
    import os,sys,anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=sys.executable,args=['-m','premise.cli','--port',str(falkordb_port),'--graph',kestrel.graph_name,'mcp'],env={**os.environ,'POLL_ENABLED':'false'})
    with anyio.fail_after(45):
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                listing=await session.list_tools()
                assert len(listing.tools)==9
                assert not any('fix' in t.name or 'write' in t.name for t in listing.tools)
                result=await session.call_tool('guarantee_health',{'id':'G_DEDUPE'})
                assert not result.isError and 'G_DEDUPE' in str(result.content)
