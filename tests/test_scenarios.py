"""T4, T5, T7, T11: every scenario in scenarios/scenarios.yaml against its ground truth."""
import pytest

from premise.scenarios import check

from conftest import SANDBOX, SCENARIOS
from helpers import scenario


@pytest.mark.parametrize("name", list(SCENARIOS["scenarios"]))
def test_scenario(kestrel, name):
    result = scenario(kestrel, SANDBOX, name)
    problems = check(result, SCENARIOS["scenarios"][name]["expect"])
    assert not problems, "\n".join(problems)


def test_diamond_reported_once(kestrel):
    """G_LEDGER_CONSISTENT reaches A_RETRY_WINDOW through two paths; it appears once with the shortest chain."""
    r = scenario(kestrel, SANDBOX, "S1")
    ledger = [g for g in r.guarantees if g.id == "G_LEDGER_CONSISTENT"]
    assert len(ledger) == 1
    assert ledger[0].chain == ["G_LEDGER_CONSISTENT", "G_CHARGE_ONCE", "G_DEDUPE", "A_RETRY_WINDOW"]


def test_superseded_decision_never_flagged(kestrel):
    """ADR-010 relies on G_DEDUPE but is superseded."""
    r = scenario(kestrel, SANDBOX, "S1")
    assert "ADR-010" not in {d.id for d in r.decisions}
    assert "ADR-010" not in {c.decision for c in r.not_affected}


def test_exposed_callers_follow_service_dependencies(kestrel):
    r = scenario(kestrel, SANDBOX, "S1")
    assert r.guarantee("G_CHARGE_ONCE").exposed_callers == ["checkoutservice", "frontend", "refundworker", "webhookingress"]


def test_decoy_vocabulary_is_ignored(kestrel):
    """S2 shares the word 'retry' with S1 but no guarantee chain; nothing is flagged."""
    r = scenario(kestrel, SANDBOX, "S2")
    assert r.verdict == "CLEAR_WITHIN_SCOPE"
    assert r.decisions == []
