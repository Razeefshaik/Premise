"""T10 routing, T13 lexical gap, T16 graph required, plus the PageRank tool."""
import re

from premise.graph.client import GraphClient, GraphUnavailable
from premise.ingest.run import ingest
from premise.reasoning.assess import assess
from premise.reasoning.models import ChangedFact

from conftest import NOW, SANDBOX
from helpers import replace_in, scenario


def _decision(result, did):
    return next(d for d in result.decisions if d.id == did)


def test_T10_routing_skips_departed_and_on_leave_people(kestrel):
    d = _decision(scenario(kestrel, SANDBOX, "S1"), "ADR-012")
    assert d.active_accountable == [] and d.departed == ["p_lena", "p_marco"]
    assert [(c.person, c.evidence) for c in d.candidates] == [("p_jun", 7), ("p_anika", 2)]
    assert "p_dev" not in {c.person for c in d.candidates}  # on leave


def test_T10_ended_membership_excludes_a_candidate(new_graph, repo_copy):
    replace_in(repo_copy, "company/people.yaml", "      - {team: t_payments, since: 2024-02-12}",
               "      - {team: t_payments, since: 2024-02-12, until: 2026-09-01}")
    c = new_graph()
    ingest(c, repo_copy)
    d = _decision(scenario(c, repo_copy, "S1"), "ADR-012")
    assert [x.person for x in d.candidates] == ["p_anika"]


def test_T10_unroutable_decision_needs_review(new_graph, repo_copy):
    for pid in ("p_anika", "p_jun"):
        replace_in(repo_copy, "company/people.yaml", f"  - id: {pid}\n    name:", f"  - id: {pid}\n    name:")
    text = (repo_copy / "company/people.yaml").read_text()
    text = text.replace("name: Anika Rao\n    status: active", "name: Anika Rao\n    status: departed")
    text = text.replace("name: Jun Park\n    status: active", "name: Jun Park\n    status: departed")
    (repo_copy / "company/people.yaml").write_text(text)
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1")
    assert any(x.code == "R_UNROUTABLE" and "ADR-012" in x.ids for x in r.reasons)
    assert r.verdict == "BLOCKED"  # missing reviewers never lower severity


def test_T13_lexical_gap(kestrel):
    """Fulltext over decision passages with S1's vocabulary finds ADR-007 and the decoy ADR-016,
    never ADR-012, ADR-015, ADR-018. The graph finds those three and excludes ADR-016."""
    hits = {r["decision"] for r in kestrel.named("search_decision_passages",
                                                  {"q": "paylane|retry|retries|window|webhook|dedupe"})}
    assert {"ADR-007", "ADR-016"} <= hits
    assert not ({"ADR-012", "ADR-015", "ADR-018"} & hits)
    flagged = {d.id for d in scenario(kestrel, SANDBOX, "S1").decisions}
    assert {"ADR-012", "ADR-015", "ADR-018"} <= flagged
    assert "ADR-016" not in flagged


def test_T13_authoring_rule_for_the_lexical_gap():
    bad = re.compile(r"\b(retry|retries|retrying|paylane|window|webhook|dedupe)\b", re.IGNORECASE)
    for adr in ("ADR-012", "ADR-015", "ADR-018"):
        body = (SANDBOX / "adr" / f"{adr}.md").read_text().split("\n---\n", 1)[1]
        assert not bad.search(body), f"{adr} body uses a forbidden word: {bad.search(body).group(0)}"


def test_T16_unreachable_graph_gives_error_verdict():
    c = GraphClient(port=1, graph_name="nowhere")
    r = assess(c, [ChangedFact(fact="x", file="f", new=1)], at_ms=NOW)
    assert r.verdict == "ERROR" and r.reasons[0].code == "R_UNAVAILABLE"


def test_T16_graph_mid_ingestion_gives_error_verdict(new_graph):
    c = new_graph()
    ingest(c, SANDBOX)
    c.write("MATCH (s:GraphState) SET s.ingest_state = 'ingesting'")
    assert assess(c, [], at_ms=NOW).verdict == "ERROR"


def test_read_queries_cannot_write(kestrel):
    try:
        kestrel.read("CREATE (:Oops)")
        raised = False
    except Exception:
        raised = True
    assert raised


def test_pagerank_ranks_load_bearing_guarantees(kestrel):
    rows = kestrel.named("load_bearing_guarantees", {"limit": 3})
    assert rows[0]["guarantee"] == "G_DEDUPE"
    assert {r["guarantee"] for r in rows[:2]} == {"G_DEDUPE", "G_CHARGE_ONCE"}
