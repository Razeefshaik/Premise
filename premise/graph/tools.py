"""Shared read-only tools. Inputs select parameters, never executable query text."""
from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict, Field
from .client import GraphUnavailable
from ..reasoning.assess import graph_ready, now_ms, _route, DAY_MS
from ..reasoning.evaluate import evaluate_assumptions, rollup
from ..agent.render import provenance
from ..reasoning.preflight import ChangeArgs, FileArgs, check_proposal


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(Args):
    pass


class Entity(Args):
    id: str = Field(min_length=1, max_length=160)


class Search(Args):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=30)


class Health(Args):
    id: str | None = Field(default=None, max_length=160)


class Limit(Args):
    limit: int = Field(default=10, ge=1, le=30)


TOOLS = {
    "check_change": ("Hypothetical: check proposed fact values against every affected guarantee. Stores nothing.", ChangeArgs),
    "check_files": ("Hypothetical: check proposed full file contents. Stores nothing and posts nothing.", FileArgs),
    "resolve": ("Resolve an entity name to graph ids", Search),
    "decision_lineage": ("Decision requirements, source evidence, lifecycle and current reviewers", Entity),
    "guarantee_health": ("Current full-prerequisite guarantee and assumption health; omit id for all", Health),
    "who_knows": ("Ownership and active experts ranked by recent authored evidence for a service", Entity),
    "search_evidence": ("Fulltext evidence passages with source citations", Search),
    "orphaned_decisions": ("Accepted decisions without active accountable people", Empty),
    "load_bearing_guarantees": ("PageRank over guarantee requirements, never used for verdicts", Limit),
    "impact_if_broken": ("Hypothetical impact if an assumption is false", Entity),
    "recall": ("Historical assessments involving an entity", Entity),
}


def terms(query):
    # Restrict Lucene syntax to literal tokens; no query operators from the caller.
    return " | ".join(dict.fromkeys(re.findall(r"[A-Za-z0-9_]+", query)))


class GraphTools:
    def __init__(self, client, at_ms=None, since_days=180):
        self.client, self.at_ms, self.since_days = client, at_ms, since_days

    @property
    def now(self):
        return self.at_ms if self.at_ms is not None else now_ms()

    def guard(self):
        ready, _, why = graph_ready(self.client)
        if not ready:
            raise GraphUnavailable(why)

    def call(self, name, arguments):
        if name not in TOOLS:
            raise ValueError("Unknown read tool")
        self.guard()
        args = TOOLS[name][1].model_validate(arguments)
        return getattr(self, name)(**args.model_dump(exclude_unset=True))

    def schemas(self):
        return [{"name":name, "description":desc, "input_schema":model.model_json_schema()} for name,(desc,model) in TOOLS.items()]

    def check_change(self, changes, include_fixes=True):
        return check_proposal(self.client, changes=changes, include_fixes=include_fixes, at_ms=self.now, since_days=self.since_days)

    def check_files(self, files, include_fixes=True):
        return check_proposal(self.client, files=files, include_fixes=include_fixes, at_ms=self.now, since_days=self.since_days)

    def resolve(self, query, limit=10):
        exact = self.client.read("MATCH (e:Entity {id:$id}) WHERE e.retired_rev IS NULL RETURN e.id AS id, labels(e) AS labels, e.search_text AS text, 1.0 AS score", {"id":query})
        return exact or (self.client.named("resolve", {"q":terms(query), "limit":limit}) if terms(query) else [])

    def guarantee_health(self, id=None):
        gids = [r["id"] for r in self.client.read("MATCH (g:Guarantee) WHERE g.retired_rev IS NULL AND ($id IS NULL OR g.id=$id) RETURN g.id AS id ORDER BY id", {"id":id})]
        if id and not gids:
            return {"outcome":"unknown_entity","id":id,"guarantees":[],"assumptions":[],"sources":[],"now_ms":self.now}
        pairs = self.client.named("guarantee_assumption_pairs", {"assumptions": None, "guarantees": gids}) if gids else []
        aids = sorted({r["assumption"] for r in pairs})
        assumptions = evaluate_assumptions(self.client, aids, {}, self.now)
        statuses = rollup(self.client, gids, assumptions)
        ranks = {r["guarantee"]:r["score"] for r in self.load_bearing_guarantees(30)}
        coverage = {g: [r["assumption"] for r in pairs if r["guarantee"] == g] for g in gids}
        return {"guarantees": sorted([{"id":g, **s, "pagerank":ranks.get(g,0), "prerequisites":coverage[g],
                 "unverified": sum(assumptions[a].state == "unverified" for a in coverage[g])} for g,s in statuses.items()], key=lambda g:(-g["pagerank"],g["id"])),
                "assumptions": [a.model_dump() for a in assumptions.values()], "now_ms":self.now,
                "sources":provenance(self.client, gids+aids)}

    def decision_lineage(self, id):
        entity = self.client.read("MATCH (d:Decision {id:$id}) WHERE d.retired_rev IS NULL RETURN properties(d) AS decision", {"id":id})
        if not entity:
            return {"outcome":"unknown_entity", "id":id}
        paths = self.client.named("decision_lineage", {"id":id})
        supersedes = self.client.read("MATCH (d:Decision {id:$id})-[r:SUPERSEDES]-(s:Decision) RETURN s.id AS id, startNode(r).id AS newer", {"id":id})
        active, gone, candidates = _route(self.client, id, self.now-self.since_days*DAY_MS)
        ids = [id] + [x for p in paths for x in [*p["chain"],*p["facts"]]]
        return {"decision":entity[0]["decision"], "paths":paths, "supersession":supersedes,
                "active_accountable":active, "unavailable":gone, "candidates":[c.model_dump() for c in candidates],
                "reviewers":active or [c.person for c in candidates], "sources":provenance(self.client,ids)}

    def who_knows(self, id):
        rows = self.client.named("who_knows", {"id":id, "since":self.now-self.since_days*DAY_MS})
        for row in rows:
            row["citations"] = self.client.named("evidence_sources", {"ids":row["sources"]}) if row["sources"] else []
        return rows

    def search_evidence(self, query, limit=10):
        return self.client.named("search_evidence", {"q":terms(query), "limit":limit}) if terms(query) else []

    def orphaned_decisions(self):
        return self.client.named("orphaned_decisions")

    def load_bearing_guarantees(self, limit=10):
        return self.client.named("load_bearing_guarantees", {"limit":limit})

    def impact_if_broken(self, id):
        if not self.client.read("MATCH (a:Assumption {id:$id}) WHERE a.retired_rev IS NULL RETURN a.id AS id", {"id":id}):
            return {"outcome":"unknown_entity","id":id,"hypothetical":True,"guarantees":[],"sources":[]}
        pairs = self.client.named("guarantee_assumption_pairs", {"assumptions":[id], "guarantees":None})
        gids = sorted({r["guarantee"] for r in pairs})
        return {"hypothetical":True, "assumption":id, "guarantees":self.client.named("guarantee_impact", {"guarantees":gids}) if gids else [],
                "sources":provenance(self.client,[id]+gids)}

    def recall(self, id):
        return self.client.named("recall", {"id":id,"limit":10})
