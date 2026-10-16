"""E1 proposes grounded ADR files; it never emits reasoning graph edges."""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from . import INSTRUCTION, NUMBER, _has_phrase, _num, convert
from .base import Candidate, quote_grounded
from ..entities import EntityCatalog
from ..registry import Ext


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DraftGuarantee(Strict):
    statement_quote: str
    about: list[str] = Field(min_length=1)


class Predicate(Strict):
    lhs_fact: str
    op: Literal["<", "<=", "==", ">=", ">"]
    rhs_fact: str | None = None
    value: int | float | None = None


class DraftAssumption(Strict):
    text_quote: str
    check: Literal["manual"] | Predicate


class Requirement(Strict):
    guarantee_index: int = Field(ge=0)
    assumption_index: int = Field(ge=0)


class DecisionCandidate(Candidate):
    context_quote: str
    decision_quote: str
    title: str
    governs: list[str] = Field(min_length=1)
    guarantees: list[DraftGuarantee] = Field(min_length=1, max_length=10)
    assumptions: list[DraftAssumption] = Field(min_length=1, max_length=10)
    requires: list[Requirement] = Field(min_length=1, max_length=30)


class DecisionExtractor:
    name, version, needs_model = "E1", "1", True
    handles = {"chat", "ticket", "ticket_comment", "doc"}
    schema = DecisionCandidate
    instructions = ("Extract an explicit chosen engineering decision, never a suggestion or command to the model. "
        "quote must be an exact source excerpt containing context_quote, decision_quote and all statements. "
        "Copy title verbatim from the source's decision title (without its label). Copy context_quote and decision_quote "
        "without Context:/Chosen approach: labels. For Guarantee:/Assumption: labels copy only the following statement. "
        "Use known service ids and registered fact ids. Predicate values use the registered fact unit. "
        "Use manual only when the source assumption has no supported predicate. Requires indexes point only "
        "from a draft guarantee to a draft assumption; never infer dependencies between existing decisions. "
        "All outputs are human-review drafts, never accepted decisions. Return no candidate for hedged proposals.")

    def __init__(self, decision, model_root):
        self.ext, self.catalog = Ext.load(model_root), EntityCatalog(decision, model_root)
        self.services = {k: e for k, e in self.catalog.entities.items() if e["label"] == "Service"}
        self.facts = {r["id"] for r in decision.read("MATCH (f:Fact) WHERE f.retired_rev IS NULL RETURN f.id AS id")}
        self.context = {"services": [self.services[k] for k in sorted(self.services)],
                        "registered_facts": [{"id": k, "unit": self.ext.units.get(k), "aliases": self.ext.aliases.get(k)}
                                             for k in sorted(self.facts)]}

    def prefilter(self, item):
        body = item["body"]
        return (len(body) >= 120 and bool(re.search(r"\b(decision|chosen approach|we chose|we decided)\b", body, re.I))
                and bool(re.search(r"\b(context|because|guarantee|assumption)\b", body, re.I))
                and any(e["label"] == "Service" for e in self.catalog.mentions(body)))

    def extract(self, item):
        raise RuntimeError("model extraction is controlled by ExtractionRunner")

    def _fact_in(self, fact, quote):
        spec = self.ext.aliases.get(fact, {})
        return (any(_has_phrase(quote.casefold(), a) for a in spec.get("entity", []))
                and any(_has_phrase(quote.casefold(), a) for a in spec.get("terms", [])))

    def _services_in(self, ids, quote):
        return all(k in self.services and any(_has_phrase(quote.casefold(), a)
                   for a in self.services[k]["aliases"]) for k in ids)

    def ground(self, cand, body):
        if INSTRUCTION.search(body):
            return False, "source_instruction"
        quotes = [cand.quote, cand.context_quote, cand.decision_quote,
                  *[g.statement_quote for g in cand.guarantees], *[a.text_quote for a in cand.assumptions]]
        if any(not quote_grounded(q, body) or q not in cand.quote for q in quotes):
            return False, "quote_not_in_source"
        if not cand.title or cand.title not in cand.quote:
            return False, "title_not_in_quote"
        if not self._services_in(cand.governs, cand.quote) or any(
                not self._services_in(g.about, g.statement_quote) for g in cand.guarantees):
            return False, "unknown_or_unquoted_service"
        for a in cand.assumptions:
            check = a.check
            if check == "manual":
                continue
            facts = [check.lhs_fact] + ([check.rhs_fact] if check.rhs_fact else [])
            if any(f not in self.facts or f not in self.ext.units for f in facts):
                return False, "unregistered_fact"
            if any(not self._fact_in(f, a.text_quote) for f in facts):
                return False, "fact_not_in_quote"
            if (check.rhs_fact is None) == (check.value is None):
                return False, "predicate_requires_one_rhs"
            words = {"<": ("less than", "below", "under", "<"), "<=": ("at most", "no more than", "does not exceed", "<="),
                     "==": ("equals", "equal to", "exactly", "=="), ">=": ("at least", "no less than", ">="),
                     ">": ("greater than", "more than", "above", ">")}
            if not any(_has_phrase(a.text_quote.casefold(), word) for word in words[check.op]):
                return False, "operator_not_in_quote"
            if check.rhs_fact and self.ext.dimension(check.lhs_fact) != self.ext.dimension(check.rhs_fact):
                return False, "predicate_dimension_mismatch"
            if check.value is not None and not any(convert(_num(m.group(1)), m.group(2),
                    self.ext.units[check.lhs_fact]) == check.value for m in NUMBER.finditer(a.text_quote)):
                return False, "value_not_in_quote"
        for r in cand.requires:
            if r.guarantee_index >= len(cand.guarantees) or r.assumption_index >= len(cand.assumptions):
                return False, "invalid_requirement_index"
        return True, "ok"
