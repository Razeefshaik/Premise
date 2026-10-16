"""Adversarial regression cases. HTTP writes use existing MockTransport, never GitHub."""
import json
import re
import time
from pathlib import Path
import pytest
import yaml
from premise.agent.analyst import answer_question
from premise.agent.render import safe
from premise.graph.tools import GraphTools
from premise.reasoning.preflight import check_proposal
from premise.ingest import yamlpos
from premise.ingest.run import ingest
from premise.reasoning.evaluate import evaluate_assumptions
from test_github import operational,Remote,HEAD
from conftest import NOW,SANDBOX

ATTACKS=yaml.safe_load((Path(__file__).resolve().parents[1]/'redteam/attacks.yaml').read_text())


@pytest.mark.parametrize('attack',ATTACKS,ids=lambda a:a['id'])
def test_attack(attack,kestrel,request,record_property,new_graph):
    category,payload=attack['category'],attack['payload']
    started=time.perf_counter()
    if category=='prompt_injection_yaml':
        result=check_proposal(kestrel,files={'config/partners/paylane.yaml':'retry:\n  window_hours: 72 # '+payload['comment']+'\n'},at_ms=NOW)
        actual=result['verdict'];assert actual=='BLOCKED'
    elif category=='prompt_injection_pr':
        _,result,remote,executor=request.getfixturevalue('operational')
        remote.pr.update(title=payload['title'],body=payload['title'])
        executor.execute(result,remote.pr)
        actual=remote.statuses[-1]['state'];assert actual=='failure'
    elif category=='link_injection':
        actual=safe(payload['text'])
        assert not re.search(r'https?://|www\.|(?<!\\)\]\(',actual,re.I)
    elif category=='mention_spam':
        actual=safe(payload['text']);assert '@' not in actual
    elif category=='path_traversal':
        with pytest.raises(ValueError):check_proposal(kestrel,files={payload['path']:'x: 1'},at_ms=NOW)
        actual='rejected'
    elif category.startswith('yaml_'):
        mode=payload['mode']
        text={'malformed':'retry: [','deep':'['*700+'0'+']'*700,'bomb':'x: &x [*x]\n'}.get(mode)
        if mode=='huge':text='x: '+'a'*10_000_000
        try:
            result=check_proposal(kestrel,files={'config/partners/paylane.yaml':text},at_ms=NOW)
            assert result['verdict']!='CLEAR_WITHIN_SCOPE' and any(r['code']=='R_UNPARSEABLE' for r in result['reasons'])
            actual=result['verdict']
        except ValueError:actual='size_rejected'
        assert time.perf_counter()-started<5
    elif category=='fake_attestation':
        graph=new_graph();ingest(graph,SANDBOX,'redteam','https://github.com/example/kestrel')
        if payload['mode']=='departed':graph.write("MATCH (p:Person)-[:ATTESTED]->(:Assumption {id:'A_STABLE_EVENT_ID'}) SET p.status='departed'")
        else:graph.write("MATCH (:Person)-[a:ATTESTED]->(:Assumption {id:'A_STABLE_EVENT_ID'}) SET a.review_by=$at",{'at':NOW-1})
        actual=evaluate_assumptions(graph,['A_STABLE_EVENT_ID'],{},NOW)['A_STABLE_EVENT_ID'].state
        assert actual=='unverified'
    elif category=='analyst_false_answer':
        class FakeAdapter:
            def tool_loop(self,system,question,schemas,dispatch,budget):
                dispatch('guarantee_health',{'id':'G_RATES_FRESH'})
                return {'outcome':'answered_with_path','answer_markdown':payload['text'],'cited_ids':['G_RATES_FRESH']}
        actual=answer_question(GraphTools(kestrel,NOW),'Health?',adapter=FakeAdapter())['mode'];assert actual=='deterministic'
    elif category=='unknown_entity':
        actual=answer_question(GraphTools(kestrel,NOW),payload['question'])['outcome'];assert actual in {'unknown_entity','not_in_graph'}
    elif category=='github_fork':
        _,result,remote,executor=request.getfixturevalue('operational')
        remote.pr['head']['repo']['full_name']='fork/kestrel';executor.execute(result,remote.pr)
        assert not remote.pulls;actual='no_fix_pr'
    elif category=='github_stale':
        from premise.github.actions import StaleAssessment
        _,result,remote,executor=request.getfixturevalue('operational')
        remote.pr['head']['sha']='b'*40
        with pytest.raises(StaleAssessment):executor.execute(result,remote.pr)
        assert not remote.pulls and not remote.comments and not remote.statuses;actual='skipped'
    elif category=='github_outage':
        import httpx
        from premise.graph.client import GraphClient
        from premise.reasoning.assess import assess
        from premise.github.api import GitHub
        from premise.github.actions import Executor
        graph=GraphClient(port=1);remote=Remote()
        github=GitHub('test/kestrel','dummy',httpx.MockTransport(remote))
        try:Executor(graph,github,auto_fix=True).execute(assess(graph,[],pr='pr:1',head_sha=HEAD),remote.pr)
        finally:github.close()
        assert remote.statuses[-1]['state']=='error' and not remote.comments and not remote.pulls;actual='error_status_only'
    elif category=='mcp_write':
        if payload['mode']=='tool':
            with pytest.raises(ValueError):GraphTools(kestrel,NOW).call('write',{'query':'DELETE'})
        else:
            from redis.exceptions import ResponseError
            with pytest.raises(ResponseError):kestrel.read('CREATE (:Injected)')
        actual='rejected'
    else:raise AssertionError('Unhandled attack category '+category)
    record_property('actual',json.dumps(actual))
    record_property('elapsed_ms',round((time.perf_counter()-started)*1000,2))
