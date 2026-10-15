"""Tests for the three review corrections.

C1: a guarantee never counts as healthy while a required manual assumption is unverified.
C2: verdicts and fixes are judged on EVERY prerequisite of each affected guarantee, including unchanged facts;
    'checked and not affected' lists only decisions whose guarantee was actually evaluated and holds.
C3: LLM configuration (no LLM code exists in this milestone; covered when the agent is added).
"""
from premise.ingest.run import ingest
from premise.reasoning.evaluate import evaluate

from conftest import NOW
from helpers import adhoc, replace_in, scenario, set_main


# ---- C1 -----------------------------------------------------------------------------------------------------------
def test_C1_red_to_green_depends_on_a_current_attestation(new_graph, repo_copy):
    """S1_FIXED is green only because A_STABLE_EVENT_ID is attested by an active person. Move the attestation to a
    departed person and the same fix can no longer turn the check green."""
    replace_in(repo_copy, "adr/ADR-007.md", "      by: p_anika", "      by: p_marco")
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1_FIXED")
    assert r.verdict == "NEEDS_REVIEW"
    assert r.assumptions_in("unverified") == ["A_STABLE_EVENT_ID"]
    assert r.by_status("unknown") == ["G_CHARGE_ONCE", "G_DEDUPE", "G_LEDGER_CONSISTENT", "G_REFUND_MATCH"]
    assert r.by_status("holds") == []


def test_C1_expired_attestation_is_unverified(new_graph, repo_copy):
    replace_in(repo_copy, "adr/ADR-007.md", "review_by: 2027-03-01", "review_by: 2026-10-01")
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1_FIXED")
    assert r.verdict == "NEEDS_REVIEW"
    assert {x.code for x in r.reasons} == {"R_UNKNOWN"}


def test_C1_main_health_reports_unverified_guarantee(kestrel):
    """On main, G_RATES_FRESH rests on an attestation that expired on 2026-09-30: unknown, not holds."""
    ev = evaluate(kestrel, {"currency.cache_ttl_minutes": 30}, NOW)  # no-op overlay to reach the guarantee
    assert ev.assumptions["A_RATE_TTL"].state == "holding"
    assert ev.assumptions["A_RATES_SOURCE"].state == "unverified"
    assert ev.status("G_RATES_FRESH") == "unknown"


# ---- C2 -----------------------------------------------------------------------------------------------------------
def test_C2_unchanged_fact_violation_is_not_hidden(new_graph, repo_copy):
    """Main already violates A_REDIS_TTL (dedupe 24h > Redis max 12h). A PR that only shortens Paylane's retry window
    touches A_RETRY_WINDOW, which holds. The affected guarantee is still broken through the unchanged fact."""
    set_main(repo_copy, "config/platform/redis.yaml", "limits.max_ttl_hours", 12)
    c = new_graph()
    ingest(c, repo_copy)
    r = adhoc(c, repo_copy, [{"op": "set", "file": "config/partners/paylane.yaml", "key": "retry.window_hours", "value": 20}])
    assert r.assumptions_in("violated") == ["A_REDIS_TTL"]
    assert next(a for a in r.assumptions if a.id == "A_RETRY_WINDOW").state == "holding"
    assert r.guarantee("G_DEDUPE").status == "broken"
    assert r.verdict == "BLOCKED"
    assert all(x.pre_existing for x in r.reasons if x.code == "R_BROKEN_T1")


def test_C2_fix_is_not_verified_while_a_prerequisite_is_unverified(new_graph, repo_copy):
    """With A_STABLE_EVENT_ID unattested, raising TTL and Redis resolves the violation but cannot make G_DEDUPE hold:
    the fix is reported as partial, never as verified."""
    replace_in(repo_copy, "adr/ADR-007.md", "      by: p_anika", "      by: p_lena")
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1")
    assert not [f for f in r.fixes if f.status == "verified"]
    assert any(f.status == "partial" and f.changes == {"webhook.dedupe_ttl_hours": 72, "redis.max_ttl_hours": 72}
               for f in r.fixes)


def test_C2_fix_must_also_repair_unchanged_fact_violations(new_graph, repo_copy):
    """Main has Redis max 12h. For S1, raising only the dedupe TTL is rejected; the verified fix must also raise Redis."""
    set_main(repo_copy, "config/platform/redis.yaml", "limits.max_ttl_hours", 12)
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1")
    verified = [f.changes for f in r.fixes if f.status == "verified"]
    assert {"webhook.dedupe_ttl_hours": 72, "redis.max_ttl_hours": 72} in verified
    assert {"webhook.dedupe_ttl_hours": 72} not in verified


def test_C2_not_affected_requires_the_sibling_to_be_evaluated_and_hold(new_graph, repo_copy):
    """Main acks too slowly (6000 ms >= Paylane's 5000 ms), so G_ACK_FAST is broken before any PR.
    ADR-016 must not be reported as 'checked and not affected' for S1; it is listed as checked with a problem."""
    set_main(repo_copy, "config/webhookingress.yaml", "ack.timeout_ms", 6000)
    c = new_graph()
    ingest(c, repo_copy)
    r = scenario(c, repo_copy, "S1")
    assert "ADR-016" not in {x.decision for x in r.not_affected}
    problem = [x for x in r.checked_with_problems if x.decision == "ADR-016"]
    assert problem and problem[0].status == "broken" and problem[0].via_guarantee == "G_ACK_FAST"
    assert "ADR-016" not in {d.id for d in r.decisions}  # still not blamed on this PR
