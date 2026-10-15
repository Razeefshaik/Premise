"""Assess a set of proposed fact changes: evaluate, propagate, route, decide, repair.

The verdict is a deterministic function of graph query results. No LLM output is consulted here.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ..graph.client import GraphClient, GraphUnavailable
from .evaluate import evaluate, evaluate_assumptions, rollup
from .models import (AssessmentResult, Candidate, ChangedFact, CheckedDecision, DecisionResult, GuaranteeResult,
                     Reason)
from .repair import Repairer

DAY_MS = 24 * 3600 * 1000


def now_ms() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def graph_ready(client: GraphClient) -> tuple[bool, int | None, str]:
    try:
        rows = client.named("graph_state")
    except Exception as exc:  # unreachable server, missing graph, timeouts
        return False, None, f"graph unavailable: {exc}"
    if not rows or rows[0]["ingest_state"] != "ready":
        state = rows[0]["ingest_state"] if rows else None
        return False, rows[0]["rev"] if rows else None, f"graph not ready (ingest_state={state})"
    return True, rows[0]["rev"], "ready"


def _route(client: GraphClient, decision_id: str, since_ms: int) -> tuple[list[str], list[str], list[Candidate]]:
    rows = client.named("route_decision", {"decision_id": decision_id, "since": since_ms})
    if not rows:
        return [], [], []
    r = rows[0]
    cands = [Candidate(**c) for c in (r["candidates"] or [])][:3]
    return sorted(r["active_accountable"] or []), sorted(r["gone"] or []), cands


def assess(client: GraphClient, changes: list[ChangedFact], *, changed_paths: list[str] | None = None,
           model_change: bool = False, at_ms: int | None = None, since_days: int = 180, pr: str | None = None,
           head_sha: str | None = None, run_repair: bool = True, fix_budget: int = 16) -> AssessmentResult:
    at = at_ms if at_ms is not None else now_ms()
    base = dict(pr=pr, head_sha=head_sha, now_ms=at, changed_facts=changes, changed_paths=changed_paths or [],
                model_change=model_change)
    ok, rev, why = graph_ready(client)
    if not ok:
        return AssessmentResult(verdict="ERROR", graph_rev=rev, reasons=[Reason(code="R_UNAVAILABLE", detail=why)], **base)
    try:
        return _assess(client, changes, at, since_days, rev, run_repair, fix_budget, base)
    except Exception as exc:
        return AssessmentResult(verdict="ERROR", graph_rev=rev,
                                reasons=[Reason(code="R_UNAVAILABLE", detail=f"assessment unavailable: {type(exc).__name__}")], **base)


def _assess(client, changes, at, since_days, rev, run_repair, fix_budget, base) -> AssessmentResult:
    overlay: dict[str, Any] = {c.fact: (None if c.deleted else c.new) for c in changes}
    ev = evaluate(client, overlay, at)

    # Baseline: the same prerequisites and guarantees evaluated on main, to tell new problems from old ones.
    base_assumptions = evaluate_assumptions(client, ev.prereqs, {}, at)
    baseline = rollup(client, ev.checked, base_assumptions)

    impact_rows = {r["guarantee"]: r for r in client.named(
        "guarantee_impact", {"guarantees": ev.checked})} if ev.checked else {}

    guarantees: list[GuaranteeResult] = []
    for gid in ev.affected:
        s = ev.statuses[gid]
        imp = impact_rows.get(gid, {})
        tiers = imp.get("tiers") or []
        guarantees.append(GuaranteeResult(
            id=gid, statement=s["statement"] or "", status=s["status"], baseline=baseline[gid]["status"],
            chain=s["chain"], tier=min(tiers) if tiers else None, promised_by=imp.get("promised_by", []),
            relied_on_by=imp.get("relied_on_by", []), about=imp.get("about", []),
            exposed_callers=sorted(imp.get("exposed_callers", [])),
        ))

    # Decisions attached to affected guarantees that do not hold.
    flagged: dict[str, DecisionResult] = {}
    for g in guarantees:
        if g.status == "holds":
            continue
        for did, role in [(d, "promises") for d in g.promised_by] + [(d, "relies_on") for d in g.relied_on_by]:
            dr = flagged.setdefault(did, DecisionResult(id=did, roles=[], via=[]))
            if role not in dr.roles:
                dr.roles.append(role)
            if g.id not in dr.via:
                dr.via.append(g.id)
    since = at - since_days * DAY_MS
    for dr in flagged.values():
        dr.roles.sort()
        dr.via.sort()
        dr.active_accountable, dr.departed, dr.candidates = _route(client, dr.id, since)
        dr.reviewers = dr.active_accountable or [c.person for c in dr.candidates]

    # Related decisions that were genuinely checked: the sibling guarantee's full prerequisite set was evaluated.
    not_affected: list[CheckedDecision] = []
    with_problems: list[CheckedDecision] = []
    for s in ev.siblings:
        if s["decision"] in flagged:
            continue
        cd = CheckedDecision(decision=s["decision"], via_guarantee=s["guarantee"], sibling_of=s["provider"],
                             status=ev.status(s["guarantee"]))
        (not_affected if cd.status == "holds" else with_problems).append(cd)

    reasons = _policy(ev, guarantees, list(flagged.values()), base["model_change"], changes)
    blocked = any(r.code == "R_BROKEN_T1" for r in reasons)
    review = any(r.code not in ("R_NO_TRACKED_FACTS", "R_ALL_HOLD") for r in reasons)
    verdict = "BLOCKED" if blocked else "NEEDS_REVIEW" if review else "CLEAR_WITHIN_SCOPE"

    result = AssessmentResult(
        verdict=verdict, graph_rev=rev, reasons=reasons, assumptions=sorted(ev.assumptions.values(), key=lambda a: a.id),
        guarantees=guarantees, decisions=sorted(flagged.values(), key=lambda d: d.id),
        not_affected=not_affected, checked_with_problems=with_problems, **base,
    )
    if run_repair and ev.violated:
        rep = Repairer(client, overlay, at, budget=fix_budget)
        result.fixes = rep.run(ev)
        result.fix_budget_used = rep.used
    return result


def _policy(ev, guarantees: list[GuaranteeResult], decisions: list[DecisionResult], model_change: bool,
            changes: list[ChangedFact]) -> list[Reason]:
    reasons: list[Reason] = []
    for g in guarantees:
        pre = g.baseline == g.status
        if g.status == "broken":
            code = "R_BROKEN_T1" if g.tier == 1 or g.tier is None else "R_BROKEN_LOW_TIER"
            reasons.append(Reason(code=code, ids=[g.id] + g.chain[-1:], pre_existing=pre,
                                  detail=f"{g.id} is broken via {' -> '.join(g.chain)}"))
        elif g.status == "unknown":
            causes = [a for a in g.chain[-1:]]
            kinds = {ev.assumptions[a].state for a in causes if a in ev.assumptions}
            reasons.append(Reason(code="R_UNKNOWN", ids=[g.id] + causes, pre_existing=pre,
                                  detail=f"{g.id} cannot be established: {', '.join(causes)} is {'/'.join(sorted(kinds))}"))
        if g.status != "holds" and not g.promised_by:
            reasons.append(Reason(code="R_NO_PROVIDER", ids=[g.id], detail=f"{g.id} has no accepted decision promising it"))
    for aid in ev.orphans:
        a = ev.assumptions[aid]
        if a.state != "holding":
            reasons.append(Reason(code="R_ORPHAN_ASSUMPTION", ids=[aid],
                                  detail=f"{aid} is {a.state} and no guarantee requires it"))
    if model_change:
        reasons.append(Reason(code="R_MODEL_CHANGE", detail="decision model files changed; applied only after merge"))
    for d in decisions:
        if not d.reviewers:
            reasons.append(Reason(code="R_UNROUTABLE", ids=[d.id], detail=f"nobody active can review {d.id}"))
    if not reasons:
        if not changes:
            reasons.append(Reason(code="R_NO_TRACKED_FACTS", detail="no tracked fact value changed"))
        else:
            n = len(ev.prereqs)
            reasons.append(Reason(code="R_ALL_HOLD", detail=f"{n} prerequisite assumptions checked; every affected guarantee holds"))
    return reasons
