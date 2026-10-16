from copy import deepcopy
from dataclasses import replace
import json
import httpx
import pytest
from premise.config import Settings
from premise.github.api import GitHub
from premise.github.poller import Pipeline
from premise.github.steward import Steward
from premise.graph.client import GraphUnavailable
from premise.ingest.run import ingest
from conftest import SANDBOX, NOW
from test_check_change import snapshot


class Issues:
    def __init__(self): self.issues=[]; self.comments={}; self.writes=[]
    def __call__(self,request):
        path=request.url.path.removeprefix('/repos/test/kestrel/')
        method=request.method
        body=json.loads(request.content) if request.content else {}
        if method!='GET': self.writes.append((method,path,body))
        if request.url.path=='/user': result={'login':'bot'}
        elif path=='issues' and method=='GET': result=self.issues
        elif path=='issues':
            result={**body,'number':len(self.issues)+1,'state':'open','user':{'login':'bot'},
                    'html_url':f'https://github.com/test/kestrel/issues/{len(self.issues)+1}'}
            self.issues.append(result)
        elif path.endswith('/comments'):
            number=int(path.split('/')[1]); comments=self.comments.setdefault(number,[])
            if method=='POST':
                result={**body,'id':len(comments)+1,'user':{'login':'bot'},'html_url':'https://github.com/test/kestrel/comment'}
                comments.append(result)
            else: result=comments
        elif path.startswith('issues/') and method=='PATCH':
            result=next(i for i in self.issues if i['number']==int(path.split('/')[1])); result.update(body)
        else: raise AssertionError((method,path))
        return httpx.Response(200,json=deepcopy(result))


@pytest.fixture
def setup_steward(new_graph):
    c=new_graph(); ingest(c,SANDBOX,'steward-main','https://github.com/test/kestrel')
    remote=Issues(); github=GitHub('test/kestrel','dummy',httpx.MockTransport(remote))
    yield c,remote,Steward(c,github,NOW)
    github.close()


def test_dry_run_exact_findings_and_graph_unchanged(setup_steward):
    c,remote,s=setup_steward; before=snapshot(c)
    plan=s.run()
    assert {(p['kind'],p['entity']) for p in plan['plan']}=={
        ('EXPIRED_ATTESTATION','A_RATES_SOURCE'),('ORPHANED_DECISION','ADR-012')}
    assert plan['writes']==0 and not remote.writes and snapshot(c)==before
    assert all(p['operation']=='create' for p in plan['plan'])
    assert '2026-09-30' in plan['plan'][0]['body']
    assert any('Jun Park' in p['body'] and 'adr/ADR-012.md:2' in p['body'] for p in plan['plan'])


def test_execute_idempotence_and_reconcile_only_operational_nodes(setup_steward):
    c,remote,s=setup_steward
    domain_before=c.read('MATCH (e:Entity) RETURN count(e) AS n')
    state_before=c.named('graph_state')
    first=s.run(execute=True)
    assert first['writes']==2 and len(remote.issues)==2
    assert all('<!-- premise:steward:' in i['body'] for i in remote.issues)
    assert all(set(body)<={'title','body'} for _,_,body in remote.writes)
    assert s.run(execute=True)['writes']==0 and len(remote.writes)==2
    c.write("MATCH (s:StewardAction) SET s.status='executing'")
    assert s.run(execute=True)['writes']==0
    assert c.read("MATCH (s:StewardAction) WHERE s.status<>'done' RETURN count(s) AS n")[0]['n']==0
    assert c.read('MATCH (e:Entity) RETURN count(e) AS n')==domain_before
    assert c.named('graph_state')==state_before


def test_resolution_closes_only_resolved_issue(setup_steward,repo_copy):
    c,remote,s=setup_steward; s.run(execute=True)
    source=repo_copy/'adr/ADR-003.md'
    source.write_text(source.read_text().replace('2026-09-30','2027-09-30'))
    ingest(c,repo_copy,'renewed','https://github.com/test/kestrel')
    before=len(remote.writes)
    result=s.run(execute=True)
    closed=[i for i in remote.issues if i['state']=='closed']
    assert len(closed)==1 and 'A_RATES_SOURCE' in closed[0]['body']
    assert 'Resolved at graph revision 2' in remote.comments[closed[0]['number']][0]['body']
    assert all(path.startswith('issues') for _,path,_ in remote.writes[before:])
    assert s.run(execute=True)['writes']==0


def test_human_closed_finding_is_suppressed(setup_steward):
    c,remote,s=setup_steward; s.run(execute=True)
    remote.issues[0]['state']='closed'
    result=s.run(execute=True)
    assert result['writes']==0 and any(p['operation']=='suppressed_by_human' for p in result['plan'])
    assert remote.issues[0]['state']=='closed'


def test_write_cap_and_neutralized_names(setup_steward,monkeypatch):
    c,remote,s=setup_steward
    example=s.findings()[0]
    examples=[]
    for index in range(12):
        f=deepcopy(example); f['entity']=f'A_SYNTH_{index}'
        f['reviewers'][0]['name']='@x [y](http://z)'
        examples.append(f)
    monkeypatch.setattr(s,'findings',lambda:examples)
    result=s.run(execute=True)
    assert result['writes']==10 and len(remote.writes)==10
    assert sum(p.get('status')=='deferred_write_cap' for p in result['plan'])==2
    assert all('@x' not in i['body'] and '[y](http://z)' not in i['body'] for i in remote.issues)


def test_unready_graph_no_remote_writes(setup_steward):
    c,remote,s=setup_steward
    c.write("MATCH (g:GraphState) SET g.ingest_state='ingesting'")
    with pytest.raises(GraphUnavailable): s.run(execute=True)
    assert not remote.writes


def test_poller_steward_disabled_and_revision_change_only(setup_steward,monkeypatch):
    c,remote,s=setup_steward
    calls=[]
    monkeypatch.setattr(Steward,'run',lambda *args,**kwargs:calls.append(kwargs))
    # Avoid GitHub PR calls; this test isolates the optional post-sync hook.
    s.github.open_pulls=lambda *args:([],None)
    p=Pipeline(c,s.github,None,replace(Settings(),steward_enabled=False))
    p.sync_main=lambda:c.write('MATCH (g:GraphState) SET g.rev=g.rev+1')
    p.once(); assert not calls
    p.settings=replace(p.settings,steward_enabled=True)
    p.once(); assert calls==[{'execute':True}]
    p.sync_main=lambda:None
    p.once(); assert len(calls)==1
    def failed_steward(*args,**kwargs): raise RuntimeError('GitHub unavailable')
    monkeypatch.setattr(Steward,'run',failed_steward)
    p.sync_main=lambda:c.write('MATCH (g:GraphState) SET g.rev=g.rev+1')
    assert p.once()==[]  # An optional issue sweep must not stop PR checks.
