from __future__ import annotations

import re
from typing import Literal

from pydantic import create_model

from . import HEDGE, NEGATION, SENTENCE
from .base import Candidate, quote_grounded
from ..entities import EntityCatalog
from ..registry import Ext, knowledge_relations


class RelationCandidate(Candidate):
    relation: str
    from_id: str
    from_mention: str
    to_id: str
    to_mention: str
    relation_words: list[str]
    action: Literal["add", "end"] = "add"
    valid_from: str | None = None
    valid_to: str | None = None


class KnowledgeExtractor:
    name, version, needs_model = "K2", "1", False
    handles = {"chat", "ticket", "ticket_comment", "doc"}
    instructions = ""

    def __init__(self, decision, model_root):
        ext = Ext.load(model_root)
        self.registry = {r["name"]: r for r in knowledge_relations(ext.relations)}
        self.catalog = EntityCatalog(decision, model_root)
        self.schema = create_model("ApprovedRelation", __base__=RelationCandidate,
                                   relation=(Literal[tuple(sorted(self.registry) + ["NONE"])], ...))
        self.context = {"approved_relations": sorted(self.registry.values(), key=lambda r: r["name"]),
                        "entities": sorted(self.catalog.entities.values(), key=lambda e: e["id"])}

    def prefilter(self, item):
        return len(self.catalog.mentions(item["body"])) >= 2

    def extract(self, item):
        candidates = []
        for m in SENTENCE.finditer(item["body"]):
            quote = m.group().strip()
            if HEDGE.search(quote):
                continue
            action = "end" if re.search(r"\b(no longer|stopped|ended)\b", quote, re.I) else "add"
            if action == "add" and NEGATION.search(quote):
                continue
            mentions = self.catalog.mentions(quote)
            for name, relation in self.registry.items():
                for alias in relation.get("aliases") or []:
                    for match in re.finditer(rf"\b{re.escape(alias)}\b", quote, re.I):
                        left = [e for e in mentions if e["label"] in relation["domain"] and e["end"] <= match.start()]
                        right = [e for e in mentions if e["label"] in relation["range"] and e["start"] >= match.end()]
                        if not left or not right:
                            continue
                        a, b = max(left, key=lambda e: e["end"]), min(right, key=lambda e: e["start"])
                        candidates.append(self.schema(quote=quote, relation=name, from_id=a["id"], from_mention=a["mention"],
                            to_id=b["id"], to_mention=b["mention"], relation_words=[match.group()], action=action))
        return list({(c.quote, c.relation, c.from_id, c.to_id, c.action): c for c in candidates}.values())

    def ground(self, cand, body):
        if not quote_grounded(cand.quote, body):
            return False, "quote_not_in_source"
        relation = self.registry.get(cand.relation)
        if not relation:
            return False, "unapproved_relation"
        if not self.catalog.resolves(cand.from_mention, cand.from_id) or not self.catalog.resolves(cand.to_mention, cand.to_id):
            return False, "unknown_entity"
        if any(mention.casefold() not in cand.quote.casefold() for mention in (cand.from_mention, cand.to_mention)):
            return False, "entity_not_in_quote"
        if self.catalog.entities[cand.from_id]["label"] not in relation["domain"] or self.catalog.entities[cand.to_id]["label"] not in relation["range"]:
            return False, "domain_range_mismatch"
        alias = any(re.search(rf"\b{re.escape(a)}\b", cand.quote, re.I) for a in relation.get("aliases", []))
        words = cand.relation_words and all(w and w.casefold() in cand.quote.casefold() for w in cand.relation_words)
        if not alias and not words:
            return False, "relation_not_in_quote"
        if HEDGE.search(cand.quote) or cand.action == "add" and NEGATION.search(cand.quote):
            return False, "nonasserted_relation"
        if cand.action == "end" and not re.search(r"\b(no longer|stopped|ended)\b", cand.quote, re.I):
            return False, "end_not_in_quote"
        for date in (cand.valid_from, cand.valid_to):
            if date and date not in cand.quote:
                return False, "date_not_in_quote"
        return True, "ok"

    def unmatched(self, item):
        found = []
        for m in SENTENCE.finditer(item["body"]):
            quote = m.group().strip()
            mentions = self.catalog.mentions(quote)
            if len(mentions) < 2 or HEDGE.search(quote) or NEGATION.search(quote):
                continue
            if self.extract({"body": quote}):
                continue
            a, b = mentions[:2]
            phrase = quote[a["end"]:b["start"]].strip(" ,:;-")
            if phrase and phrase.casefold() not in {"and", "or"}:
                found.append({"quote": quote, "phrase": phrase[:160], "domain_label": a["label"], "range_label": b["label"]})
        return found


class KnowledgeModelExtractor(KnowledgeExtractor):
    name, needs_model = "K2_LLM", True
    instructions = ("For unmatched sentences, extract only approved descriptive relations or NONE. "
                    "Both entity mentions and the exact relation_words must be copied from the quote. "
                    "Never propose relation types. Do not emit REQUIRES, PROVIDES or RELIES_ON. "
                    "Leave dates null unless a literal date appears in the quote. End a row only for an explicit ending.")

    def prefilter(self, item):
        unmatched = self.unmatched(item)
        self.context["unmatched_sentences"] = [m["quote"] for m in unmatched]
        return bool(unmatched)
