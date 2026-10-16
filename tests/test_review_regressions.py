"""Leader review probes converted to regressions for the corrected behaviour."""
from dataclasses import replace
from types import SimpleNamespace

from premise.agent.analyst import answer_question
from premise.agent.render import render_comment
from premise.agent.verify import verify_answer
from premise.config import Settings
from premise.graph.tools import GraphTools
from premise.ingest.run import ingest
from premise.reasoning.intake import overlay_from_files
from premise.reasoning.models import AssessmentResult, ChangedFact, Reason
from premise.github.poller import Pipeline
from premise.github.gitrepo import PRFiles

from conftest import NOW, SANDBOX
from helpers import replace_in
import pytest
from premise.agent.render import safe
from premise.graph.client import GraphUnavailable
from premise.reasoning.assess import assess

ORIGINAL = (SANDBOX / "config/webhookingress.yaml").read_text()


def test_P1_stale_branch_preserves_unedited_main_values(new_graph, repo_copy):
    """Main advanced ack.timeout_ms; the stale PR's TTL edit must preserve that value."""
    replace_in(repo_copy, "config/webhookingress.yaml", "timeout_ms: 2000", "timeout_ms: 2500")
    c = new_graph()
    ingest(c, repo_copy)
    pr_head_text = ORIGINAL.replace("ttl_hours: 24", "ttl_hours: 72")  # branched before main's change
    changes, _, _ = overlay_from_files(c, {"config/webhookingress.yaml": pr_head_text},
                                     base_files={"config/webhookingress.yaml": ORIGINAL})
    assert {ch.fact for ch in changes} == {"webhook.dedupe_ttl_hours"}
    assert (changes[0].old, changes[0].new) == (24, 72)


def test_P2_malformed_yaml_is_reviewed_once_per_head(kestrel):
    statuses = []
    pr = {"number": 9, "state": "open", "title": "t", "head": {"sha": "c" * 40, "ref": "x", "repo": {"full_name": "o/r"}},
          "base": {"ref": "main", "repo": {"full_name": "o/r"}}}
    state = kestrel.named("graph_state")[0]
    github = SimpleNamespace(repo="o/r", pull=lambda n: pr, open_pulls=lambda etag=None: ([pr], None),
                             status=lambda sha, st, desc, url="": statuses.append((st, desc)) or {})
    git = SimpleNamespace(root=SANDBOX, main=lambda: state["main_sha"],
                          pr_files=lambda n, sha, main: PRFiles(
                              {"config/webhookingress.yaml": "dedupe: [unclosed"},
                              {"config/webhookingress.yaml": ORIGINAL}))
    p = Pipeline(kestrel, github, git, replace(Settings(), anthropic_api_key=""))
    # Only status writes are needed for this poll regression; retain the real graph cursor.
    p.executor.execute = lambda result, pr: github.status(result.head_sha, "failure", result.reasons[0].detail)
    results = [p.once() for _ in range(3)]
    assert len(statuses) == 2
    assert results[0][0].verdict == "NEEDS_REVIEW" and results[1:] == [[], []]
    assert results[0][0].reasons[0].code == "R_UNPARSEABLE"
    assert "config/webhookingress.yaml:1:" in statuses[1][1]


def test_P3_grounding_check_is_id_only(kestrel):
    rows = [{"tool": "guarantee_health", "arguments": {}, "rows": GraphTools(kestrel, NOW).call("guarantee_health", {})}]
    false_claim = {"outcome": "answered_with_path", "cited_ids": ["G_DEDUPE"],
                   "answer_markdown": "G_DEDUPE is broken and nobody should merge anything."}
    assert not verify_answer(false_claim, rows)
    harmless = {"outcome": "answered_with_path", "cited_ids": [],
                "answer_markdown": "G_DEDUPE holds, e.g. under current facts."}
    assert verify_answer(harmless, rows)


def test_P4_answer_without_tool_calls_uses_deterministic_fallback(kestrel):
    class NoTools:
        def tool_loop(self, system, question, schemas, dispatch, budget):
            return {"outcome": "answered_with_path", "cited_ids": ["ADR-012"],
                    "answer_markdown": "ADR-012 was written by p_jun."}  # never called a tool
    out = answer_question(GraphTools(kestrel, NOW), "Who wrote ADR-012?", adapter=NoTools())
    assert out["mode"] == "deterministic"
    assert "was written by p_jun" not in out["answer_markdown"]


def test_P5_pr_controlled_string_cannot_render_as_link():
    r = AssessmentResult(verdict="NEEDS_REVIEW", pr="pr:1", head_sha="a" * 40, graph_rev=1,
                         reasons=[Reason(code="R_UNKNOWN", detail="x")],
                         changed_facts=[ChangedFact(fact="webhook.dedupe_ttl_hours", file="f", old=24,
                                                    new="[Approve here](https://evil.example)")])
    comment = render_comment(r, 1, "http://x")
    assert "[Approve here](https://evil.example)" not in comment
    assert r"\[Approve here\]\(https://evil.example\)" in comment


def test_pr_comment_escapes_mentions_and_code_fences():
    assert '@' not in safe('@everyone @reviewer')
    assert safe('```\n[approve](https://evil.example)') == r'\`\`\` \[approve\]\(https://evil.example\)'


@pytest.mark.parametrize('head,base,expected',[
    (None,ORIGINAL,{'webhook.dedupe_ttl_hours','webhook.ack_timeout_ms'}),
    (ORIGINAL.replace('ttl_hours: 24','ttl_hours: true'),ORIGINAL,{'webhook.dedupe_ttl_hours'}),
    (ORIGINAL,ORIGINAL,set()),
    (ORIGINAL,None,{'webhook.dedupe_ttl_hours','webhook.ack_timeout_ms'}),
])
def test_merge_base_overlay_handles_deletion_type_change_and_addition(kestrel,head,base,expected):
    changes,_,_=overlay_from_files(kestrel,{'config/webhookingress.yaml':head},
                                 base_files={'config/webhookingress.yaml':base})
    # Added files whose values equal current main need no overlay.
    if base is None:
        expected=set()
    assert {c.fact for c in changes}==expected


def test_malformed_file_does_not_discard_other_file_edits(kestrel):
    issues=[]
    changes,_,_=overlay_from_files(kestrel,{
        'config/webhookingress.yaml':'dedupe: [unclosed',
        'config/emailservice.yaml':(SANDBOX/'config/emailservice.yaml').read_text().replace('max_attempts: 5','max_attempts: 8')
    },issues=issues)
    assert {c.fact for c in changes}=={'emailservice.retry_max_attempts'}
    assert len(issues)==1 and issues[0].code=='R_UNPARSEABLE'


def test_error_cursor_backoff_retries_and_new_heads_bypass_wait(kestrel,monkeypatch):
    clock=[1_000_000]
    monkeypatch.setattr('premise.github.poller.now_ms',lambda:clock[0])
    current={'number':99,'head':{'sha':'a'*40}}
    github=SimpleNamespace(repo='o/r',open_pulls=lambda etag=None:([current], 'etag'))
    p=Pipeline(kestrel,github,None,replace(Settings(),anthropic_api_key=''))
    p.sync_main=lambda:None
    p.executor.reconcile=lambda:[]
    calls=[]
    def unavailable(number,execute):
        calls.append(current['head']['sha'])
        return AssessmentResult(pr=f'pr:{number}',head_sha=current['head']['sha'],verdict='ERROR')
    p.assess_pr=unavailable
    assert len(p.once())==1 and p.once()==[]
    first=p.store.cursor()['errors']['99']
    assert first['retry_at']==clock[0]+60_000
    # A new Pipeline instance still honors the graph-backed retry cursor.
    p2=Pipeline(kestrel,github,None,Settings())
    p2.sync_main=p.sync_main; p2.executor.reconcile=lambda:[]; p2.assess_pr=unavailable
    assert p2.once()==[]
    clock[0]+=60_000
    assert len(p2.once())==1
    assert p2.store.cursor()['errors']['99']['retry_at']==clock[0]+120_000
    current['head']['sha']='b'*40
    assert len(p2.once())==1 and len(calls)==3
    assert p2.store.cursor()['errors']['99']['attempts']==1


def test_main_outage_statuses_back_off(kestrel,monkeypatch):
    clock=[1_000_000]
    monkeypatch.setattr('premise.github.poller.now_ms',lambda:clock[0])
    pr={'number':1,'state':'open','head':{'sha':'a'*40}}
    statuses=[]
    github=SimpleNamespace(repo='o/r',open_pulls=lambda:([pr],None),pull=lambda n:pr,
                           status=lambda *args:statuses.append(args))
    p=Pipeline(kestrel,github,None,Settings())
    def outage(): raise GraphUnavailable('offline')
    p.sync_main=outage
    with pytest.raises(GraphUnavailable): p.once()
    assert p.once()==[] and len(statuses)==1
    clock[0]+=60_000
    with pytest.raises(GraphUnavailable): p.once()
    assert len(statuses)==2


def test_unexpected_reasoning_error_logs_traceback(kestrel,monkeypatch,caplog):
    def bug(*args,**kwargs): raise KeyError('regression-marker')
    monkeypatch.setattr('premise.reasoning.assess._assess',bug)
    result=assess(kestrel,[])
    assert result.verdict=='ERROR' and result.reasons[0].code=='R_INTERNAL_ERROR'
    assert 'KeyError' in result.reasons[0].detail
    assert any(record.exc_info for record in caplog.records)


def test_fresh_graph_bootstraps_without_hiding_query_bugs(new_graph,monkeypatch):
    from premise import bootstrap
    from premise.reasoning.assess import graph_ready
    from redis.exceptions import ResponseError
    client=new_graph()
    assert graph_ready(client)[0] is False
    monkeypatch.setattr(bootstrap,'GraphClient',lambda *args:client)
    monkeypatch.setattr(bootstrap,'settings',lambda:replace(Settings(),poll_enabled=False,
        sandbox_dir=str(SANDBOX),anthropic_api_key=''))
    starts=[]
    monkeypatch.setattr(bootstrap.uvicorn,'run',lambda *args,**kwargs:starts.append(kwargs))
    bootstrap.main()
    assert graph_ready(client)[0] and starts[0]['port']==8000
    with pytest.raises(ResponseError):
        client.read('THIS IS NOT CYPHER')


@pytest.mark.parametrize('text,valid',[
    ('G_DEDUPE holds.',True),
    ('G_DEDUPE is broken.',False),
    ('G_DEDUPE is not broken.',False),
    ('G_DEDUPE is unknown.',False),
    ('G_DEDUPE holds, i.e. its prerequisites hold.',True),
    ('Every guarantee holds.',False),  # G_RATES_FRESH is unknown.
    ('G_RATES_FRESH is unknown.',True),
])
def test_explicit_health_claims_match_tool_rows(kestrel,text,valid):
    rows=[{'tool':'guarantee_health','arguments':{},'rows':GraphTools(kestrel,NOW).call('guarantee_health',{})}]
    assert verify_answer({'outcome':'answered_with_path','answer_markdown':text,'cited_ids':[]},rows)==valid


def test_llm_summary_discloses_verification_limits(kestrel):
    class UsesTools:
        def tool_loop(self,system,question,schemas,dispatch,budget):
            dispatch('guarantee_health',{'id':'G_DEDUPE'})
            return {'outcome':'answered_with_path','answer_markdown':'G_DEDUPE holds.','cited_ids':['G_DEDUPE']}
    out=answer_question(GraphTools(kestrel,NOW),'Does G_DEDUPE hold?',adapter=UsesTools())
    assert out['mode']=='llm' and 'other claims not verified' in out['verification']
