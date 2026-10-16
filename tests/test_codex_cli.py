"""Offline contract tests; real model tests are explicitly invoked by the rehearsal script."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from premise.agent import codex_cli
from premise.agent.analyst import answer_question
from premise.agent.codex_cli import CodexAdapter, CodexUnavailable, Step, parse_events, run_cli
from premise.agent.fix_agent import augment_fixes
from premise.agent.llm import Adapter, make_adapter
from premise.config import Settings
from premise.graph.tools import GraphTools
from premise.scenarios import run_scenario
from premise.web.app import create_app
from conftest import SANDBOX, SCENARIOS, NOW


def events(step, complete=True):
    rows=[{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(step)}}]
    if complete:
        rows.append({'type':'turn.completed','usage':{'input_tokens':20,'output_tokens':10}})
    return '\n'.join(json.dumps(row) for row in rows)


def final(answer):
    return {'kind':'final','name':'','arguments_json':'{}','answer_json':json.dumps(answer)}


def tool(name,args):
    return {'kind':'tool_call','name':name,'arguments_json':json.dumps(args),'answer_json':''}


def script(monkeypatch,steps):
    captured=[]
    monkeypatch.setattr(codex_cli,'resolve_binary',lambda _: 'native-codex')
    def run(command,prompt,cwd,timeout):
        captured.append({'command':command,'prompt':json.loads(prompt.split('\n',1)[1]),'cwd':cwd,'timeout':timeout})
        assert Path(cwd,'step.schema.json').exists()
        return events(steps.pop(0))
    monkeypatch.setattr(codex_cli,'run_cli',run)
    return captured


def test_provider_selection_is_explicit_and_anthropic_stays_default(monkeypatch):
    monkeypatch.delenv('LLM_PROVIDER',raising=False)
    assert Settings().llm_provider=='anthropic'
    config=replace(Settings(),llm_provider='codex-cli',anthropic_api_key='')
    assert config.llm_enabled and isinstance(make_adapter(config),CodexAdapter)
    assert isinstance(make_adapter(replace(config,llm_provider='anthropic',anthropic_api_key='dummy')),Adapter)
    assert not replace(config,llm_provider='none').llm_enabled
    with pytest.raises(ValueError): replace(config,llm_provider='typo')
    with pytest.raises(ValueError): replace(config,codex_timeout_seconds=0)


def test_host_dispatch_and_inference_only_cli_flags(monkeypatch):
    captured=script(monkeypatch,[tool('read',{'id':'G_DEDUPE'}),final({'answer':'healthy'})])
    calls=[]
    def dispatch(name,args):
        calls.append((name,args))
        return {'id':args['id'],'status':'holds'}
    adapter=CodexAdapter(model='explicit-model')
    assert adapter.tool_loop('system','question',[{'name':'read'}],dispatch,1)=={'answer':'healthy'}
    assert calls==[('read',{'id':'G_DEDUPE'})]
    command=captured[0]['command']
    assert command[command.index('--sandbox')+1]=='read-only'
    assert {'--ignore-user-config','--ignore-rules','--json','--ephemeral','--skip-git-repo-check','--output-schema'} <= set(command)
    assert 'features.shell_tool=false' in command and 'features.unified_exec=false' in command
    assert 'mcp_servers={}' in command and 'features.apps=false' in command
    assert '--model' in command and 'explicit-model' in command
    assert captured[0]['prompt']['tool_results']==[]
    assert captured[1]['prompt']['tool_results'][0]['rows']['status']=='holds'
    assert captured[1]['prompt']['remaining_tool_calls']==0
    assert not Path(captured[0]['cwd']).exists()
    assert adapter.trace[0]['usage']=={'input_tokens':20,'output_tokens':10}


@pytest.mark.parametrize('steps,budget',[
    ([tool('write',{})],1),
    ([tool('read',{})],0),
    ([tool('read',{}),tool('read',{})],1),
])
def test_unlisted_tools_and_budget_overflow_never_dispatch(monkeypatch,steps,budget):
    script(monkeypatch,steps)
    calls=[]
    with pytest.raises(CodexUnavailable):
        CodexAdapter().tool_loop('s','q',[{'name':'read'}],lambda *args:calls.append(args),budget)
    assert len(calls)<=budget and all(name=='read' for name,_ in calls)


def test_invalid_arguments_are_returned_as_tool_errors(monkeypatch):
    captured=script(monkeypatch,[tool('read',{'bad':True}),final({'answer':'unavailable'})])
    def dispatch(*args): raise ValueError('sensitive source text')
    CodexAdapter().tool_loop('s','q',[{'name':'read'}],dispatch,1)
    assert captured[1]['prompt']['tool_results'][0]['rows']=={'error':'ValueError'}


@pytest.mark.parametrize('output',[
    events(final({'answer':'x'}),complete=False),
    json.dumps({'type':'turn.failed','error':{'message':'provider error'}}),
    json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'write'}}),
    json.dumps({'type':'item.completed','item':{'type':'mcp_tool_call'}}),
    events({'kind':'final','name':'','arguments_json':'{}','answer_json':'{}','extra':True}),
])
def test_failed_incomplete_native_or_nonconforming_output_rejected(output):
    with pytest.raises((ValueError,CodexUnavailable)):
        parse_events(output)


def test_child_does_not_receive_application_secrets(monkeypatch,tmp_path):
    for name in ['GITHUB_TOKEN','GH_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY']:
        monkeypatch.setenv(name,'must-not-reach-child')
    command=[sys.executable,'-c',"import os,json; print(json.dumps({k:v for k,v in os.environ.items() if v=='must-not-reach-child'}))"]
    assert json.loads(run_cli(command,'',str(tmp_path),5))=={}


def test_process_timeout_and_output_bounds(tmp_path,monkeypatch):
    with pytest.raises(CodexUnavailable,match='timed out'):
        run_cli([sys.executable,'-c','import time; time.sleep(30)'],'',str(tmp_path),0.2)
    monkeypatch.setattr(codex_cli,'MAX_OUTPUT',128)
    with pytest.raises(CodexUnavailable,match='output exceeds'):
        run_cli([sys.executable,'-c',"print('x'*1024)"],'',str(tmp_path),5)


def test_missing_or_failing_cli_preserves_deterministic_fixes(kestrel,monkeypatch):
    config=replace(Settings(),llm_provider='codex-cli',anthropic_api_key='')
    def fail(_): raise CodexUnavailable('not installed')
    monkeypatch.setattr(codex_cli,'resolve_binary',fail)
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    before=[fix.model_dump() for fix in result.fixes]
    augment_fixes(kestrel,result,config)
    assert [fix.model_dump() for fix in result.fixes]==before
    answer=answer_question(GraphTools(kestrel,NOW),'Who reviews ADR-012?',config)
    assert answer['mode']=='deterministic' and answer['provider_error']=='CodexUnavailable'
    assert 'p_jun' in answer['answer_markdown']


def test_codex_answer_uses_real_graph_tool_and_verifier(kestrel,monkeypatch):
    captured=script(monkeypatch,[tool('guarantee_health',{'id':'G_DEDUPE'}),final({
        'outcome':'answered_with_path','answer_markdown':'G_DEDUPE holds.','cited_ids':['G_DEDUPE']})])
    config=replace(Settings(),llm_provider='codex-cli',anthropic_api_key='')
    out=answer_question(GraphTools(kestrel,NOW),'Does G_DEDUPE hold?',config)
    assert out['mode']=='llm' and out['provider']=='codex-cli' and out['sources']
    assert len(captured)==2


def test_codex_fix_must_pass_test_fix_before_acceptance(kestrel,monkeypatch):
    good={'webhook.dedupe_ttl_hours':72,'redis.max_ttl_hours':72}
    script(monkeypatch,[tool('test_fix',{'changes':good}),final({'fixes':[{'changes':good}]})])
    result=run_scenario(kestrel,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    result.fixes=[]
    augment_fixes(kestrel,result,replace(Settings(),llm_provider='codex-cli',anthropic_api_key=''))
    assert len(result.fixes)==1 and result.fixes[0].origin=='llm' and result.fixes[0].status=='verified'


def test_exact_replay_cache_uses_current_tool_rows(kestrel,monkeypatch):
    captured=script(monkeypatch,[tool('read',{}),final({'ok':True})])
    def execute(row):
        return CodexAdapter(graph=kestrel).tool_loop('unique-cache-test','q',[{'name':'read'}],lambda *_:row,1)
    assert execute({'state':'first'})=={'ok':True}
    assert len(captured)==2
    # Read tools still execute on a replay. Different evidence must trigger new inference.
    assert execute({'state':'first'})=={'ok':True} and len(captured)==2
    captured.clear()
    script(monkeypatch,[final({'ok':False})])
    assert execute({'state':'changed'})=={'ok':False}


def test_web_exposes_codex_configuration_without_requiring_anthropic(kestrel):
    config=replace(Settings(),poll_enabled=False,llm_provider='codex-cli',anthropic_api_key='')
    with TestClient(create_app(kestrel,config)) as client:
        assert 'Model provider configured: codex-cli' in client.get('/').text
