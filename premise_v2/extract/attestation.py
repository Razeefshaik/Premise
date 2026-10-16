from __future__ import annotations

from typing import Literal

from .base import Candidate, content_words, quote_grounded


class AssumptionEvidence(Candidate):
    assumption_id: str
    stance: Literal["supports", "contradicts", "unrelated"]
    stance_words: list[str]


class AttestationExtractor:
    name, version, needs_model = "E3", "1", True
    handles = {"chat", "ticket", "ticket_comment", "doc"}
    schema = AssumptionEvidence
    instructions = ("Extract evidence about the listed manual assumptions. Use only their registered ids. "
                    "Copy the exact words carrying the stance into stance_words. An example contradiction is "
                    "a new event_id on every retry against an assumption promising the same event_id.")

    def __init__(self, decision):
        self.manual = {r["id"]: r["text"] for r in decision.read(
            "MATCH (a:Assumption) WHERE a.check_kind='manual' AND a.retired_rev IS NULL RETURN a.id AS id, a.text AS text ORDER BY id")}
        self.context = {"manual_assumptions": self.manual}

    def prefilter(self, item):
        words = content_words(item["body"])
        return any(len(words & content_words(text)) >= 2 for text in self.manual.values())

    def extract(self, item):
        raise RuntimeError("model extraction is controlled by ExtractionRunner")

    def ground(self, cand, body):
        if not quote_grounded(cand.quote, body):
            return False, "quote_not_in_source"
        if cand.assumption_id not in self.manual:
            return False, "unknown_or_predicate_assumption"
        if not cand.stance_words or any(not word or word.casefold() not in cand.quote.casefold() for word in cand.stance_words):
            return False, "stance_words_not_in_quote"
        if len(content_words(cand.quote) & content_words(self.manual[cand.assumption_id])) < 2:
            return False, "assumption_not_in_quote"
        return True, "ok"
