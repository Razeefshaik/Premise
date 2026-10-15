"""Apply scenario patches to the company repo and check Premise's assessment against stated ground truth."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .graph.client import GraphClient
from .ingest import yamlpos as yp
from .ingest.parse import to_ms
from .reasoning.assess import assess
from .reasoning.intake import overlay_from_files
from .reasoning.models import AssessmentResult


def load_scenarios(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def apply_patches(root: Path, patches: list[dict[str, Any]]) -> dict[str, str | None]:
    changed: dict[str, str | None] = {}
    for p in patches:
        current = changed.get(p["file"], (root / p["file"]).read_text())
        if p["op"] == "set":
            changed[p["file"]] = yp.set_value(current, p["key"], p["value"])
        elif p["op"] == "delete":
            changed[p["file"]] = yp.delete_key(current, p["key"])
        elif p["op"] == "append":
            changed[p["file"]] = current + p["text"]
        else:
            raise ValueError(f"unknown patch op {p['op']}")
    return changed


def run_scenario(client: GraphClient, root: Path, scenario: dict[str, Any], now: int, since_days: int = 180) -> AssessmentResult:
    changed = apply_patches(root, scenario["patches"])
    facts, paths, model_change = overlay_from_files(client, changed)
    return assess(client, facts, changed_paths=paths, model_change=model_change, at_ms=now, since_days=since_days,
                  pr=scenario.get("title"))


def check(result: AssessmentResult, expect: dict[str, Any]) -> list[str]:
    """Return a list of mismatches between the result and the ground truth (empty means pass)."""
    bad: list[str] = []

    def eq(name: str, got: Any, want: Any) -> None:
        if got != want:
            bad.append(f"{name}: expected {want}, got {got}")

    if "verdict" in expect:
        eq("verdict", result.verdict, expect["verdict"])
    if "reasons" in expect:
        eq("reasons", sorted({r.code for r in result.reasons}), sorted(expect["reasons"]))
    for state in ("violated", "unevaluable", "unverified"):
        if state in expect:
            eq(state, result.assumptions_in(state), sorted(expect[state]))
    for status in ("broken", "unknown", "holds"):
        if status in expect:
            eq(status, result.by_status(status), sorted(expect[status]))
    for gid, chain in (expect.get("chains") or {}).items():
        g = result.guarantee(gid)
        eq(f"chain {gid}", g.chain if g else None, chain)
    if "flagged" in expect:
        eq("flagged", {d.id: d.roles for d in result.decisions}, expect["flagged"] or {})
    for did in expect.get("not_flagged", []):
        if any(d.id == did for d in result.decisions):
            bad.append(f"{did} must not be flagged")
    if "not_affected" in expect:
        eq("not_affected", sorted(c.decision for c in result.not_affected), sorted(expect["not_affected"]))
    for did, people in (expect.get("reviewers") or {}).items():
        d = next((x for x in result.decisions if x.id == did), None)
        got = (d.reviewers if d.active_accountable else [c.person for c in d.candidates]) if d else None
        eq(f"reviewers {did}", got, people)
    for want in expect.get("fixes_verified", []):
        if not any(f.status == "verified" and f.changes == want for f in result.fixes):
            bad.append(f"missing verified fix {want}; got {[(f.status, f.changes) for f in result.fixes]}")
    for want in expect.get("fixes_rejected", []):
        if not any(f.status == "rejected" and f.changes == want for f in result.fixes):
            bad.append(f"missing rejected fix {want}")
    for fact in expect.get("fixes_never_touch", []):
        if any(fact in f.changes for f in result.fixes):
            bad.append(f"a fix touches forbidden fact {fact}")
    for code in expect.get("pre_existing", []):
        if not any(r.code == code and r.pre_existing for r in result.reasons):
            bad.append(f"reason {code} should be marked pre_existing")
    return bad


def scenario_now(data: dict[str, Any]) -> int:
    return to_ms(data["now"])
