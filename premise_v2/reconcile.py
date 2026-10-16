"""Reconciler: compare grounded claims with the decision graph (read only) and find drift.

Rules from the research:
* Independence: claims from the same person, the same thread, or items that link to each other
  (a Slack message quoting PAY-311 and PAY-311 itself) are ONE origin, however many times repeated.
* Support levels: observed (1 independent asserting origin) < corroborated (2 or more).
  ``contested`` is a separate flag: an independent origin denies the value or asserts another one.
* Three clocks: the world time a source states (as_of), when Premise saw it, and when the model's
  value last changed. The model time is the commit of the exact YAML line (git blame), not the file.
  Claims older than the model's line say nothing new and are ignored.
* Memory: a (fact, value) a human already rejected is not proposed again unless newer evidence appears.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from premise.graph.client import GraphClient
from premise.ingest import yamlpos as yp

from .staging import Staging

TICKET_REF = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


@dataclass
class Drift:
    fact: str
    file: str
    key: str
    line: int | None
    model_value: object
    value: object
    unit: str
    controlled_by: str
    support: str                     # observed | corroborated
    contested: bool
    origins: list[list[str]]         # independent origin clusters of supporting items
    supporting: list[dict] = field(default_factory=list)
    disagreeing: list[dict] = field(default_factory=list)
    weak: list[dict] = field(default_factory=list)          # hedged or instruction-like mentions
    model_as_of_ms: int | None = None
    as_of_unknown: bool = False
    previously_rejected: dict | None = None

    @property
    def key_id(self) -> str:
        return f"{self.fact}={self.value}"


def line_commit_ms(model_root: Path, rel_path: str, line: int | None) -> int | None:
    """Commit time of one line via git blame; None when the model repo is not a git checkout."""
    if not line:
        return None
    try:
        out = subprocess.run(["git", "-C", str(model_root), "blame", "--porcelain", "-L", f"{line},{line}", "--", rel_path],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode:
        return None
    m = re.search(r"^committer-time (\d+)$", out.stdout, re.M)
    if not m or "0000000000000000000000000000000000000000" in out.stdout.split("\n", 1)[0]:
        return None                  # uncommitted line
    return int(m.group(1)) * 1000


def _origins(claims: list[dict], items_by_ref: dict[str, str]) -> list[list[str]]:
    uf = _UnionFind()
    for c in claims:
        k = c["envelope_key"]
        uf.find(k)
        uf.union(k, f"person:{c['person']}")
        uf.union(k, f"thread:{c.get('item_thread') or k}")
        for ref in TICKET_REF.findall(c.get("item_text") or ""):
            target = items_by_ref.get(ref)
            if target and target != k:
                uf.union(k, target)
                uf.union(k, f"thread:{target}")
        if c["envelope_key"].startswith("jira:"):
            root = c["envelope_key"].split("#")[0]
            uf.union(k, f"thread:{root}")
    groups: dict[str, list[str]] = {}
    for c in claims:
        groups.setdefault(uf.find(c["envelope_key"]), []).append(c["envelope_key"])
    return sorted(sorted(set(v)) for v in groups.values())


def _evidence(c: dict) -> dict:
    return {k: c.get(k) for k in ("envelope_key", "url", "person", "quote", "status", "as_of_ms", "value", "raw",
                                  "previous", "supersedes", "source", "container", "visibility", "account")}


def reconcile(staging: Staging, decision: GraphClient, model_root: str | Path) -> tuple[list[Drift], list[dict]]:
    """Returns (drifts, confirmations). Reads the decision graph only through RO queries."""
    model_root = Path(model_root)
    from .identity import IdentityDirectory
    claims = IdentityDirectory(staging, decision, model_root).resolve_claims(staging.active_claims())
    facts = {r["id"]: r for r in decision.named("facts_by_id", {"ids": sorted({c["fact"] for c in claims})})} if claims else {}
    items_by_ref = {}
    for c in claims:
        if c["envelope_key"].startswith("jira:"):
            items_by_ref[c["envelope_key"].split(":", 1)[1].split("#")[0]] = c["envelope_key"].split("#")[0]
    for row in staging.c.read("MATCH (i:Item) WHERE i.source='jira' AND NOT i.deleted RETURN i.key AS k"):
        items_by_ref.setdefault(row["k"].split(":", 1)[1].split("#")[0], row["k"].split("#")[0])

    drifts, confirmations = [], []
    by_fact: dict[str, list[dict]] = {}
    for c in claims:
        by_fact.setdefault(c["fact"], []).append(c)
    for fact, fclaims in sorted(by_fact.items()):
        f = facts.get(fact)
        if not f:
            continue
        model_value = f["value"]
        line = f.get("line")
        _, vnode = yp.find(yp.compose((model_root / f["file"]).read_text(encoding="utf-8")), f["key"]) \
            if (model_root / f["file"]).exists() else (None, None)
        line = yp.line(vnode) if vnode is not None else line
        model_ms = line_commit_ms(model_root, f["file"], line)
        fresh = [c for c in fclaims if model_ms is None or c["as_of_ms"] > model_ms]
        for c in fclaims:
            if c["status"] == "asserted" and c["value"] == model_value:
                confirmations.append(_evidence(c) | {"fact": fact})
        values = sorted({c["value"] for c in fresh if c["status"] == "asserted" and c["value"] != model_value}, key=str)
        for value in values:
            support = [c for c in fresh if c["status"] == "asserted" and c["value"] == value]
            origins = _origins(support, items_by_ref)
            supporting_keys = {c["envelope_key"] for c in support}
            deny = [c for c in fresh if (c["status"] == "negated" and c["value"] == value)
                    or (c["status"] == "asserted" and c["value"] != value)]
            groups = _origins(support + deny, items_by_ref)
            deny_independent = [c for c in deny
                                if not any(c["envelope_key"] in g and set(g) & supporting_keys for g in groups)]
            weak = [c for c in fresh if c["status"] in {"hedged", "instruction"}]
            key = f"{fact}={value}"
            rejected = staging.rejection(key)
            if rejected and not any(c["as_of_ms"] > rejected["at_ms"] for c in support):
                previously = rejected
            else:
                previously = None
            drifts.append(Drift(
                fact=fact, file=f["file"], key=f["key"], line=line, model_value=model_value, value=value,
                unit=support[0]["unit"], controlled_by=f["controlled_by"],
                support="corroborated" if len(origins) >= 2 else "observed", contested=bool(deny_independent),
                origins=origins, supporting=[_evidence(c) for c in support], disagreeing=[_evidence(c) for c in deny],
                weak=[_evidence(c) for c in weak], model_as_of_ms=model_ms, as_of_unknown=model_ms is None,
                previously_rejected=previously))
    return drifts, confirmations
