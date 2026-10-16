"""The ext/ registry files, and the firewall between Kind 1 and Kind 2 relations.

Kind 1 (reasoning) relations are a CODE CONSTANT. Verdict code names them directly and never reads
the registry, so no registry change can alter a verdict. The registry may only mirror them, and
``check_relations`` fails if it does not mirror them exactly. Kind 2 (knowledge) relations are data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REASONING_RELATIONS = frozenset({"REQUIRES", "PROVIDES", "RELIES_ON"})
BANNED_NAMES = frozenset({"RELATED_TO", "ASSOCIATED_WITH", "HAS", "IS", "LINKED_TO", "CONNECTED_TO"})
RETIREMENT_REASONS = frozenset({"duplicate", "ambiguous", "erroneous", "outdated"})
NODE_LABELS = frozenset({"Decision", "Guarantee", "Assumption", "Fact", "Person", "Team", "Service", "Partner",
                         "Source", "Ticket", "Incident", "Runbook"})
UNIT_DIMENSIONS = {"ms": "time", "seconds": "time", "minutes": "time", "hours": "time", "days": "time", "count": "count"}


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


@dataclass
class Ext:
    root: Path
    units: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    identities: dict[str, dict[str, str]] = field(default_factory=dict)
    relations: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, model_root: str | Path) -> "Ext":
        root = Path(model_root) / "ext"

        def read(name: str) -> Any:
            p = root / name
            return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None

        return cls(root=root, units=read("fact_units.yaml") or {}, aliases=read("fact_aliases.yaml") or {},
                   identities=(read("identities.yaml") or {}).get("people", {}),
                   relations=read("relations.yaml") or {"registry_version": 0, "relations": []})

    def dimension(self, fact: str) -> str | None:
        return UNIT_DIMENSIONS.get(self.units.get(fact, ""))


def check_relations(registry: dict[str, Any]) -> list[str]:
    """Return every rule violation. CI runs this; an empty list means the registry is acceptable."""
    errors: list[str] = []
    entries = registry.get("relations") or []
    names = [e.get("name", "") for e in entries]
    by_name = {e.get("name"): e for e in entries}
    if len(names) != len(set(names)):
        errors.append("relation names must be unique")
    reasoning = {e["name"] for e in entries if e.get("kind") == "reasoning"}
    if reasoning != REASONING_RELATIONS:
        errors.append(f"reasoning relations {sorted(reasoning)} must equal the code constant {sorted(REASONING_RELATIONS)}")
    reasoning_norm = {_norm(n) for n in REASONING_RELATIONS}
    for e in entries:
        name, kind, status = e.get("name", ""), e.get("kind"), e.get("status")
        where = f"relation {name or '<unnamed>'}"
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            errors.append(f"{where}: name must be UPPER_SNAKE")
        if kind not in {"reasoning", "knowledge"}:
            errors.append(f"{where}: kind must be reasoning or knowledge")
        if status not in {"proposed", "approved", "deprecated", "retired"}:
            errors.append(f"{where}: unknown status {status}")
        if kind == "reasoning" and (status != "approved" or e.get("locked") is not True):
            errors.append(f"{where}: reasoning relations must be approved and locked")
        if name in BANNED_NAMES:
            errors.append(f"{where}: vague names are not allowed")
        for side in ("domain", "range"):
            values = e.get(side) or []
            if status != "retired" and (not values or any(v not in NODE_LABELS for v in values)):
                errors.append(f"{where}: {side} must list known node labels")
        if kind == "knowledge":
            spellings = [name] + list(e.get("aliases") or [])
            if any(_norm(s) in reasoning_norm for s in spellings):
                errors.append(f"{where}: name or alias collides with a reasoning relation")
            if status == "approved":
                ex = e.get("examples") or {}
                if len(ex.get("positive") or []) < 2 or len(ex.get("negative") or []) < 1:
                    errors.append(f"{where}: approved knowledge relations need 2 positive and 1 negative examples")
        if status == "retired":
            if e.get("retirement_reason") not in RETIREMENT_REASONS:
                errors.append(f"{where}: retired relations need a retirement_reason")
            if e.get("retirement_reason") == "duplicate":
                target = by_name.get(e.get("same_as"))
                if not target or target.get("status") != "approved":
                    errors.append(f"{where}: same_as must point to an approved relation")
    return errors


def knowledge_relations(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Approved Kind 2 relations, the list an extractor may use. Never includes reasoning relations."""
    return [e for e in registry.get("relations") or []
            if e.get("kind") == "knowledge" and e.get("status") == "approved" and e.get("name") not in REASONING_RELATIONS]
