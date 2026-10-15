"""Real FalkorDB memory plus HTTP-level GitHub mocks; no external writes."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from dataclasses import replace

import httpx
import pytest
from premise.config import Settings
from premise.github.api import GitHub, GitHubError
from premise.github.actions import Executor, StaleAssessment
from premise.github.gitrepo import GitRepo
from premise.github.poller import Pipeline
from premise.github.store import Store, assessment_id
from premise.ingest.run import ingest
from premise.scenarios import run_scenario
from conftest import SANDBOX, SCENARIOS, NOW

HEAD="a"*40


def pr(number=1):
    return {"number":number,"title":"Partner policy change","state":"open",
            "head":{"sha":HEAD,"ref":"scenario/s1","repo":{"full_name":"test/kestrel"}},
            "base":{"ref":"main","repo":{"full_name":"test/kestrel"}}}


class Remote:
    def __init__(self):
        self.pr=pr()
        self.comments=[]
        self.statuses=[]
        self.pulls=[]
        self.branches={}
        self.commits={HEAD:{"sha":HEAD,"tree":{"sha":"base-tree"},"parents":[]}}
        self.trees=[]
        self.requests=[]
    def __call__(self,req):
        self.requests.append((req.method,req.url.path))
        path=req.url.path.removeprefix('/repos/test/kestrel/')
        body=json.loads(req.content) if req.content else {}
        data={}
        if req.url.path=='/user': data={"login":"owner"}
        elif path=='pulls/1': data=self.pr
        elif path.startswith('statuses/'):
            self.statuses.append(body); data={"target_url":body.get("target_url","")}
        elif path=='issues/1/comments':
            if req.method=='POST':
                self.comments.append({"id":len(self.comments)+1,**body,"user":{"login":"owner"},"html_url":"https://github.com/test/kestrel/issues/1#issuecomment-1"})
                data=self.comments[-1]
            else: data=self.comments
        elif path.startswith('issues/comments/'):
            self.comments[0].update(body); data=self.comments[0]
        elif path=='pulls':
            if req.method=='GET': data=[self.pr] if req.url.params.get('state')=='open' and not req.url.params.get('head') else self.pulls
            else:
                self.pulls.append({"number":2,**body,"html_url":"https://github.com/test/kestrel/pull/2"})
                data=self.pulls[-1]
        elif path.startswith('contents/'):
            text=(SANDBOX/path.removeprefix('contents/')).read_bytes()
            data={"content":base64.b64encode(text).decode(),"sha":"blob"}
        elif path=='git/trees':
            self.trees.append(body); data={"sha":"new-tree"}
        elif path=='git/commits' and req.method=='POST':
            data={"sha":"new-commit","tree":{"sha":body["tree"]},"parents":[{"sha":s} for s in body["parents"]]}
            self.commits[data["sha"]]=data
        elif path.startswith('git/commits/'):
            data=self.commits[path.split('/')[-1]]
        elif path=='git/refs':
            self.branches[body['ref'].removeprefix('refs/heads/')]=body['sha']; data=body
        elif path.startswith('git/ref/heads/'):
            branch=path.removeprefix('git/ref/heads/')
            if branch not in self.branches: return httpx.Response(404,json={})
            data={"object":{"sha":self.branches[branch]}}
        else:
            raise AssertionError(f"Unexpected API call {req.method} {path}")
        return httpx.Response(200,json=deepcopy(data))


@pytest.fixture
def operational(new_graph):
    client=new_graph()
    ingest(client,SANDBOX,'c'*40,'https://github.com/test/kestrel')
    result=run_scenario(client,SANDBOX,SCENARIOS['scenarios']['S1'],NOW)
    result.pr='pr:1'; result.head_sha=HEAD
    remote=Remote()
    github=GitHub('test/kestrel','dummy-test-token',httpx.MockTransport(remote))
    return client,result,remote,Executor(client,github,auto_fix=True)


def test_status_comment_fix_and_main_isolation(operational):
    client,result,remote,executor=operational
    output=executor.execute(result,remote.pr)
    assert remote.statuses[-1]['state']=='failure'
    assert remote.statuses[-1]['context']=='premise/decisions'
    assert len(remote.comments)==1 and len(remote.pulls)==1
    comment=remote.comments[0]['body']
    assert all(id in comment for id in ['ADR-012','ADR-015','ADR-018','ADR-016','A_REDIS_TTL'])
    assert 'Checked and not affected' in comment and 'mermaid' in comment
    assert '#L' in comment and '@p_' not in comment
    assert f'/blob/{HEAD}/config/partners/paylane.yaml#L' in comment
    assert remote.pulls[0]['base']=='scenario/s1'
    assert len(remote.trees[0]['tree'])==2  # atomic complete remedy
    assert {f['value'] for f in client.named('facts_by_id',{'ids':['webhook.dedupe_ttl_hours']})}=={24}
    assert output['fix_pr'].endswith('/pull/2')
    assert client.read("MATCH (a:Action) RETURN count(a) AS n")[0]['n']==3


def test_idempotency_and_crash_reconciliation(operational):
    client,result,remote,executor=operational
    executor.execute(result,remote.pr)
    client.write("MATCH (a:Action) SET a.status='executing'")
    outcomes=executor.reconcile()
    assert outcomes
    assert len(remote.comments)==1 and len(remote.pulls)==1
    executor.execute(result,remote.pr)
    assert len(remote.comments)==1 and len(remote.pulls)==1
    assert client.read("MATCH (a:Action) WHERE a.status<>'done' RETURN count(a) AS n")[0]['n']==0


def test_comment_updated_for_new_revision(operational):
    client,result,remote,executor=operational
    executor.auto_fix=False
    executor.execute(result,remote.pr)
    ingest(client,SANDBOX,'mainsha2','https://github.com/test/kestrel')
    result.graph_rev+=1
    executor.execute(result,remote.pr)
    assert len(remote.comments)==1
    assert f'Graph revision {result.graph_rev}' in remote.comments[0]['body']
    assert ('PATCH','/repos/test/kestrel/issues/comments/1') in remote.requests


@pytest.mark.parametrize('change',['head','revision','closed'])
def test_stale_actions_skipped(operational,change):
    client,result,remote,executor=operational
    if change=='head': remote.pr['head']['sha']='b'*40
    elif change=='closed': remote.pr['state']='closed'
    else: client.write("MATCH (s:GraphState) SET s.rev=s.rev+1")
    with pytest.raises(StaleAssessment): executor.execute(result,remote.pr)
    assert not remote.comments and not remote.statuses and not remote.pulls
    assert client.read("MATCH (a:Action {status:'skipped'}) RETURN count(a) AS n")[0]['n']==1


def test_graph_not_ready_only_error_status(operational):
    client,_,remote,executor=operational
    client.write("MATCH (s:GraphState) SET s.ingest_state='ingesting'")
    from premise.reasoning.assess import assess
    result=assess(client,[],pr='pr:1',head_sha=HEAD)
    executor.execute(result,remote.pr)
    assert result.verdict=='ERROR' and remote.statuses[-1]['state']=='error'
    assert not remote.comments and not remote.pulls


def test_graph_outage_only_error_status():
    from premise.graph.client import GraphClient
    from premise.reasoning.assess import assess
    client=GraphClient(port=1)
    result=assess(client,[],pr='pr:1',head_sha=HEAD)
    remote=Remote()
    executor=Executor(client,GitHub('test/kestrel','dummy',httpx.MockTransport(remote)),auto_fix=True)
    executor.execute(result,remote.pr)
    assert remote.statuses[-1]['state']=='error' and not remote.comments and not remote.pulls


def test_fork_and_partial_remedies_never_open_pr(operational):
    _,result,remote,executor=operational
    remote.pr['head']['repo']['full_name']='fork/kestrel'
    executor.execute(result,remote.pr)
    assert not remote.pulls
    remote.pr['head']['repo']['full_name']='test/kestrel'
    for fix in result.fixes: fix.status='partial'
    executor.execute(result,remote.pr)
    assert not remote.pulls


def test_fix_executor_rejects_external_and_unverified(operational):
    _,result,remote,executor=operational
    with pytest.raises(ValueError): executor.fix_pr(result,remote.pr,{'paylane.retry_window_hours':24})
    with pytest.raises(ValueError): executor.fix_pr(result,remote.pr,{'webhook.dedupe_ttl_hours':72})
    assert not remote.trees and not remote.pulls


def test_git_intake_only_own_diff(tmp_path):
    origin=tmp_path/'origin'; origin.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(origin),*args],stderr=subprocess.DEVNULL).decode().strip()
    git('init','-b','main'); git('config','user.name','test'); git('config','user.email','test@example.com')
    (origin/'fact.yaml').write_text('value: 24\n')
    git('add','.'); git('commit','-m','base'); git('checkout','-b','scenario')
    (origin/'fact.yaml').write_text('value: 72\n'); git('commit','-am','change')
    head=git('rev-parse','HEAD'); git('update-ref','refs/pull/1/head',head)
    git('checkout','main'); (origin/'unrelated.md').write_text('main only'); git('add','.'); git('commit','-m','main advance')
    repo=GitRepo(tmp_path/'managed',str(origin))
    main=repo.main(); files=repo.pr_files(1,head,main)
    assert files=={'fact.yaml':'value: 72\n'}
    with pytest.raises(RuntimeError): repo.pr_files(1,'f'*40,main)


def test_api_conditional_poll_and_rate_limit():
    def handler(req):
        if req.headers.get('if-none-match'): return httpx.Response(304)
        return httpx.Response(403,json={'message':'rate limit'})
    github=GitHub('test/kestrel','dummy',httpx.MockTransport(handler))
    assert github.open_pulls('etag')==(None,'etag')
    with pytest.raises(GitHubError,match='HTTP 403'): github.open_pulls()


def test_poller_reassesses_new_main_revision(operational):
    client,result,remote,executor=operational
    class Git:
        root=SANDBOX
        sha='1'*40
        def main(self): return self.sha
        def pr_files(self,*args): return {'config/partners/paylane.yaml':'retry:\n  window_hours: 72\ndelivery:\n  timeout_ms: 5000\n'}
    git=Git()
    pipeline=Pipeline(client,executor.github,git,Settings(auto_fix_pr=False))
    pipeline.once()
    before=client.named('graph_state')[0]['rev']
    git.sha='2'*40
    pipeline.once()
    assert client.named('graph_state')[0]['rev']==before+1
    assert len(remote.comments)==1
