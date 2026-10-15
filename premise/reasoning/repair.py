"""Deterministic fix search. Every candidate is verified with test_fix, which re-runs the full graph evaluation:
all prerequisites of every affected guarantee (including unchanged facts and manual attestations) must hold.

Rules enforced here, not in any prompt:
  * only facts controlled_by 'us', numeric values only, at most 3 facts per fix
  * never change an external fact, never set a changed fact straight back to its main value (that is a revert)
  * violations whose facts are disjoint are repaired independently (clusters), then combined and verified as a whole
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from ..graph.client import GraphClient
from .evaluate import Evaluation, evaluate
from .models import AssumptionResult, Fix

MAX_FACTS_PER_FIX = 3
MAX_COMBINED = 3


@dataclass
class FixTest:
    changes: dict[str, Any]
    evaluation: Evaluation


class Repairer:
    def __init__(self, client: GraphClient, base_overlay: dict[str, Any], now_ms: int, budget: int = 16):
        self.client = client
        self.base = dict(base_overlay)
        self.now = now_ms
        self.budget = budget
        self.used = 0
        self._facts: dict[str, dict[str, Any]] = {}

    # -- graph backed helpers ------------------------------------------------------------------------------------
    def facts(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        missing = sorted(i for i in ids if i not in self._facts)
        if missing:
            for r in self.client.named("facts_by_id", {"ids": missing}):
                self._facts[r["id"]] = r
        return {i: self._facts[i] for i in ids if i in self._facts}

    def test_fix(self, changes: dict[str, Any]) -> FixTest | None:
        """Full re-evaluation with the PR overlay plus the proposed changes. None when the budget is spent."""
        if self.used >= self.budget:
            return None
        self.used += 1
        return FixTest(changes, evaluate(self.client, {**self.base, **changes}, self.now))

    # -- candidate generation --------------------------------------------------------------------------------------
    def candidates(self, a: AssumptionResult, already: dict[str, Any]) -> list[dict[str, Any]]:
        """Set the controllable side of one violated predicate exactly to its bound."""
        if a.kind != "predicate" or not _num(a.lv) or not _num(a.rv):
            return []
        info = self.facts({f for f in (a.lhs_fact, a.rhs_fact) if f})
        out: list[dict[str, Any]] = []
        strict_step = 1 if isinstance(a.lv, int) and isinstance(a.rv, int) else 1e-3
        lhs_target = {"<": a.rv - strict_step, "<=": a.rv, ">": a.rv + strict_step, ">=": a.rv, "==": a.rv}[a.op]
        rhs_target = {"<": a.lv + strict_step, "<=": a.lv, ">": a.lv - strict_step, ">=": a.lv, "==": a.lv}[a.op]
        for fact, target in ((a.lhs_fact, lhs_target), (a.rhs_fact, rhs_target)):
            if not fact or fact in already or fact not in info:
                continue
            f = info[fact]
            if f["controlled_by"] != "us" or f["value_type"] not in ("int", "float"):
                continue
            if fact in self.base and target == f["value"]:
                continue  # a straight revert of the PR's own change is always possible and is not a fix
            if f["value_type"] == "int":
                target = int(target)
            out.append({**already, fact: target})
        return [c for c in out if len(c) <= MAX_FACTS_PER_FIX]

    # -- search ----------------------------------------------------------------------------------------------------
    def run(self, ev: Evaluation) -> list[Fix]:
        violated = [a for a in ev.assumptions.values() if a.state == "violated" and a.kind == "predicate"]
        if not violated:
            return []
        base_bad = set(ev.violated)
        base_unknown = set(ev.unknown)
        fixes: list[Fix] = []
        cluster_fixes: list[list[dict[str, Any]]] = []

        for cluster in _clusters(violated):
            ids = {a.id for a in cluster}
            ok: list[dict[str, Any]] = []
            frontier = [c for a in cluster for c in self.candidates(a, {})]
            for depth in (1, 2):
                nxt: list[dict[str, Any]] = []
                for cand in _dedupe(frontier):
                    t = self.test_fix(cand)
                    if t is None:
                        break
                    still = ids & set(t.evaluation.violated)
                    new_bad = set(t.evaluation.violated) - base_bad
                    new_unknown = set(t.evaluation.unknown) - base_unknown
                    if not still and not new_bad and not new_unknown:
                        ok.append(cand)
                        if t.evaluation.all_hold:
                            fixes.append(Fix(changes=cand, status="verified"))
                        continue
                    failed = sorted(still | new_bad | new_unknown)
                    fixes.append(Fix(changes=cand, status="rejected", failed=failed))
                    if depth == 1:
                        for aid in sorted(still | new_bad):
                            nxt.extend(self.candidates(t.evaluation.assumptions[aid], cand))
                if ok:
                    break
                frontier = nxt
            cluster_fixes.append(sorted(ok, key=lambda c: self._cost(c)))

        clusters_with_fix = [c for c in cluster_fixes if c]
        if len(cluster_fixes) > 1 and len(clusters_with_fix) == len(cluster_fixes):
            for combo in itertools.islice(itertools.product(*[c[:2] for c in cluster_fixes]), MAX_COMBINED):
                merged: dict[str, Any] = {}
                for part in combo:
                    merged.update(part)
                if len(merged) > MAX_FACTS_PER_FIX:
                    continue
                t = self.test_fix(merged)
                if t is None:
                    break
                if t.evaluation.all_hold:
                    fixes.append(Fix(changes=merged, status="verified", rationale="combined fix for independent violations"))
                else:
                    fixes.append(Fix(changes=merged, status="rejected",
                                     failed=sorted(set(t.evaluation.violated) | set(t.evaluation.unknown))))
        # A cluster fix that resolved its own violations without making every affected guarantee hold is partial:
        # either other clusters remain, or a guarantee still has an unverified or unevaluable prerequisite.
        many = len(cluster_fixes) > 1
        for cand_list in cluster_fixes:
            for cand in cand_list:
                if not any(f.changes == cand for f in fixes):
                    fixes.append(Fix(changes=cand, status="partial",
                                     rationale="resolves one of several independent violations" if many else
                                     "resolves the violation, but an affected guarantee still cannot be verified"))
        return _rank(fixes, self._cost)

    def _cost(self, changes: dict[str, Any]) -> tuple[int, float]:
        info = self.facts(set(changes))
        rel = 0.0
        for f, v in changes.items():
            cur = self.base.get(f, info.get(f, {}).get("value"))
            if _num(cur) and _num(v):
                rel += abs(v - cur) / max(abs(cur), 1)
        return (len(changes), round(rel, 6))


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clusters(violated: list[AssumptionResult]) -> list[list[AssumptionResult]]:
    groups: list[tuple[set[str], list[AssumptionResult]]] = []
    for a in violated:
        facts = {f for f in (a.lhs_fact, a.rhs_fact) if f}
        merged = [g for g in groups if g[0] & facts]
        rest = [g for g in groups if not (g[0] & facts)]
        new_facts = set(facts)
        members = [a]
        for g in merged:
            new_facts |= g[0]
            members += g[1]
        groups = rest + [(new_facts, members)]
    return [sorted(m, key=lambda x: x.id) for _, m in sorted(groups, key=lambda g: min(x.id for x in g[1]))]


def _dedupe(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for c in cands:
        key = tuple(sorted(c.items()))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _rank(fixes: list[Fix], cost) -> list[Fix]:
    order = {"verified": 0, "partial": 1, "rejected": 2}
    unique: dict[tuple, Fix] = {}
    for f in fixes:
        key = (f.status, tuple(sorted(f.changes.items())))
        unique.setdefault(key, f)
    return sorted(unique.values(), key=lambda f: (order[f.status], cost(f.changes)))
