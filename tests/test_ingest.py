"""T9, T14, T15: validation limits, idempotent revisions with sweep, provenance lines."""
import re
from pathlib import Path

import pytest

from premise.ingest.run import IngestionError, ingest
from premise.reasoning.assess import assess

from conftest import NOW, SANDBOX
from helpers import replace_in, scenario


def _chain_adr(depth: int) -> str:
    """An ADR whose guarantees form a REQUIRES chain of `depth` edges ending in one assumption."""
    gs = [f"G_C{i}" for i in range(depth)]
    provides = []
    for i, g in enumerate(gs):
        req = gs[i + 1] if i + 1 < depth else "A_CHAIN"
        provides.append(f"  - id: {g}\n    statement: chain {i}\n    about: [adservice]\n    requires: [{req}]")
    relies = ", ".join(gs[1:])
    return ("---\nid: ADR-099\ntitle: Chain\nstatus: accepted\ndecided: 2026-01-01\nauthors: [p_kim]\napprovers: []\n"
            "governs: [adservice]\nsupersedes: []\n" f"relies_on: [{relies}]\nprovides:\n" + "\n".join(provides) +
            "\nassumptions:\n  - id: A_CHAIN\n    text: chain\n    check: {lhs: adservice.cache_ttl_seconds, op: \"<=\", rhs_const: 300}\n---\n# Chain\n")


def test_T9_depth_six_is_accepted(new_graph, repo_copy):
    (repo_copy / "adr" / "ADR-099.md").write_text(_chain_adr(6))
    c = new_graph()
    ingest(c, repo_copy)
    rows = c.read("MATCH p=(g:Guarantee {id:'G_C0'})-[:REQUIRES*1..6]->(a:Assumption {id:'A_CHAIN'}) RETURN length(p) AS n")
    assert rows == [{"n": 6}]


def test_T9_depth_seven_is_rejected_and_graph_not_ready(new_graph, repo_copy):
    (repo_copy / "adr" / "ADR-099.md").write_text(_chain_adr(7))
    c = new_graph()
    with pytest.raises(IngestionError) as exc:
        ingest(c, repo_copy)
    assert any("7 edges deep" in e for e in exc.value.errors)
    assert assess(c, [], at_ms=NOW).verdict == "ERROR"


def test_T9_cycle_is_rejected(new_graph, repo_copy):
    replace_in(repo_copy, "adr/ADR-007.md",
               "requires: [A_RETRY_WINDOW, A_REDIS_TTL, A_STABLE_EVENT_ID]",
               "requires: [A_RETRY_WINDOW, A_REDIS_TTL, A_STABLE_EVENT_ID, G_REFUND_MATCH]")
    c = new_graph()
    with pytest.raises(IngestionError) as exc:
        ingest(c, repo_copy)
    assert any("cycle" in e for e in exc.value.errors)


def test_T9_attestation_without_date_is_rejected(new_graph, repo_copy):
    replace_in(repo_copy, "adr/ADR-007.md", "      date: 2026-09-02", "      on: 2026-09-02")
    with pytest.raises(IngestionError) as exc:
        ingest(new_graph(), repo_copy)
    assert any("attestation needs" in e for e in exc.value.errors)


def test_T14_reingest_is_idempotent(new_graph):
    c = new_graph()
    a = ingest(c, SANDBOX)
    b = ingest(c, SANDBOX)
    assert (b.rev, b.node_count, b.edge_count) == (a.rev + 1, a.node_count, a.edge_count)


def test_T14_sweep_removes_edges_not_reasserted(new_graph, repo_copy):
    c = new_graph()
    ingest(c, repo_copy)
    assert "ADR-016" not in {d.id for d in scenario(c, repo_copy, "S1").decisions}
    replace_in(repo_copy, "adr/ADR-016.md", "relies_on: [G_ACK_FAST]", "relies_on: [G_DEDUPE]")
    ingest(c, repo_copy)
    assert c.read("MATCH (:Decision {id:'ADR-016'})-[r:RELIES_ON]->(g) RETURN g.id AS g") == [{"g": "G_DEDUPE"}]
    flagged = {d.id: d.roles for d in scenario(c, repo_copy, "S1").decisions}
    assert flagged["ADR-016"] == ["relies_on"]


def test_T15_every_claim_points_at_the_right_line(kestrel):
    rows = kestrel.read("""
        MATCH (n)-[r:STATED_IN]->(s:Source) WHERE n:Decision OR n:Guarantee OR n:Assumption
        RETURN n.id AS id, s.path AS path, r.line AS line""")
    assert len(rows) == 11 + 9 + 10
    for r in rows:
        text = (SANDBOX / r["path"]).read_text().splitlines()[r["line"] - 1]
        assert r["id"] in text, (r, text)
    facts = kestrel.read("MATCH (f:Fact)-[r:DEFINED_IN]->(s:Source) RETURN f.key AS key, s.path AS path, r.line AS line")
    assert len(facts) == 12
    for f in facts:
        text = (SANDBOX / f["path"]).read_text().splitlines()[f["line"] - 1]
        assert re.match(rf"\s*{re.escape(f['key'].split('.')[-1])}:", text), (f, text)


def test_validation_warnings(kestrel):
    import json
    warnings = json.loads(kestrel.read("MATCH (s:GraphState) RETURN s.warnings_json AS w")[0]["w"])
    assert "orphan assumption A_CART_TTL: no guarantee requires it" in warnings
    assert "orphaned decision ADR-012: nobody accountable is still active" in warnings
