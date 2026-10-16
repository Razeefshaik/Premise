"""Graph evaluation of a set of proposed fact values.

Steps (all graph queries):
  1. touched     = assumptions whose predicate reads a changed fact
  2. affected    = every guarantee with a REQUIRES chain (1..6) down to a touched assumption
  3. siblings    = guarantees provided by the same accepted decisions as affected ones, plus their reliers
  4. checked     = affected + siblings
  5. prereqs     = EVERY assumption reachable from any checked guarantee, plus touched ones
                   (unchanged facts included: a guarantee is judged on all of its prerequisites)
  6. evaluate all prereqs under the overlay (predicates by comparison, manual ones by current attestation)
  7. roll up each checked guarantee with three valued AND: broken > unknown > holds
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..graph.client import GraphClient
from .models import AssumptionResult


@dataclass
class Evaluation:
    touched: list[str]
    affected: list[str]
    orphans: list[str]
    siblings: list[dict[str, Any]]
    checked: list[str]
    prereqs: list[str]
    assumptions: dict[str, AssumptionResult]
    statuses: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def violated(self) -> list[str]:
        return sorted(a for a, r in self.assumptions.items() if r.state == "violated")

    @property
    def unknown(self) -> list[str]:
        return sorted(a for a, r in self.assumptions.items() if r.state in ("unevaluable", "unverified"))

    def status(self, gid: str) -> str:
        return self.statuses[gid]["status"]

    @property
    def all_hold(self) -> bool:
        """True only if every affected guarantee holds and every touched assumption holds."""
        return all(self.status(g) == "holds" for g in self.affected) and all(
            self.assumptions[a].state == "holding" for a in self.touched
        )


def overlay_param(overlay: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"fact": f, "to": v} for f, v in sorted(overlay.items())]


def evaluate_assumptions(client: GraphClient, ids: list[str], overlay: dict[str, Any], now_ms: int,
                         touched: set[str] | None = None, gone: list[str] | None = None) -> dict[str, AssumptionResult]:
    if not ids:
        return {}
    rows = client.named("evaluate_assumptions", {"ids": sorted(ids), "overlay": overlay_param(overlay), "now": now_ms, "gone": gone or []})
    out: dict[str, AssumptionResult] = {}
    for r in rows:
        holds = r["holds"]
        if holds is True:
            state = "holding"
        elif holds is False:
            state = "violated"
        else:
            state = "unverified" if r["kind"] == "manual" else "unevaluable"
        out[r["id"]] = AssumptionResult(
            id=r["id"], kind=r["kind"], state=state, text=r["text"] or "", lhs_fact=r["lhs_fact"], lv=r["lv"],
            op=r["op"], rhs_fact=r["rhs_fact"], rv=r["rv"], attestations=r["atts"] or [],
            touched=bool(touched and r["id"] in touched),
        )
    return out


def rollup(client: GraphClient, guarantees: list[str], assumptions: dict[str, AssumptionResult]) -> dict[str, dict]:
    if not guarantees:
        return {}
    violated = [a for a, r in assumptions.items() if r.state == "violated"]
    unknown = [a for a, r in assumptions.items() if r.state in ("unevaluable", "unverified")]
    rows = client.named("rollup_guarantees", {"guarantees": sorted(guarantees), "violated": violated, "unknown": unknown})
    return {r["guarantee"]: {"status": r["status"], "chain": r["chain"], "statement": r["statement"]} for r in rows}


def evaluate(client: GraphClient, overlay: dict[str, Any], now_ms: int) -> Evaluation:
    fact_ids = sorted(overlay)
    touched = [r["id"] for r in client.named("touched_assumptions", {"facts": fact_ids})] if fact_ids else []
    up = client.named("guarantee_assumption_pairs", {"assumptions": touched, "guarantees": None}) if touched else []
    affected = sorted({r["guarantee"] for r in up})
    orphans = sorted(set(touched) - {r["assumption"] for r in up})
    siblings = client.named("siblings", {"affected": affected}) if affected else []
    checked = sorted(set(affected) | {s["guarantee"] for s in siblings})
    down = client.named("guarantee_assumption_pairs", {"assumptions": None, "guarantees": checked}) if checked else []
    prereqs = sorted({r["assumption"] for r in down} | set(touched))
    assumptions = evaluate_assumptions(client, prereqs, overlay, now_ms, set(touched))
    ev = Evaluation(touched=touched, affected=affected, orphans=orphans, siblings=siblings, checked=checked,
                    prereqs=prereqs, assumptions=assumptions)
    ev.statuses = rollup(client, checked, assumptions)
    return ev
