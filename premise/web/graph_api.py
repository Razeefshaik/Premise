"""Read-only, whitelisted graph exploration. Health is the existing engine's output."""
from __future__ import annotations

from copy import deepcopy
from threading import RLock

from fastapi import APIRouter, Query, Path
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ..agent.render import provenance
from ..graph.client import GraphUnavailable
from ..graph.recorder import QueryRecorder
from ..graph.tools import GraphTools

KINDS = {"reasoning": ("Decision", "Guarantee", "Assumption"), "people": ("Person", "Team"),
         "services": ("Service",), "facts": ("Fact",)}
LABELS = [label for labels in KINDS.values() for label in labels]
EDGE_TYPES = frozenset("REQUIRES PROVIDES RELIES_ON ABOUT GOVERNS ACCOUNTABLE_FOR OWNS MEMBER_OF LHS RHS ATTESTED DEPENDS_ON".split())


class UnknownEntity(Exception):
    pass


class InvalidKinds(Exception):
    pass


class GraphRoute(APIRoute):
    """Invalid input executes no queries, but still carries the trace envelope."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return JSONResponse({"error": "invalid_request", "graph_rev": None, "nodes": [], "edges": [],
                    "truncated": False, "queries": [],
                    "validation": [{"loc": e["loc"], "type": e["type"]} for e in exc.errors()]}, status_code=422)
        return handle


class GraphExplorer:
    def __init__(self, client, at_ms=None, node_cap=300):
        if type(node_cap) is not int or not 1 <= node_cap <= 300:
            raise ValueError("node cap must be between 1 and 300")
        self.client, self.tools, self.cap = client, GraphTools(client, at_ms), node_cap
        self._cache, self._lock = None, RLock()

    def _state(self):
        row = self.client.named("graph_state")[0]
        if row["ingest_state"] != "ready":
            raise GraphUnavailable("graph has no ready revision")
        return row["rev"], row["main_sha"]

    def _health(self, state):
        now = self.tools.now
        with self._lock:
            cache = self._cache
            if cache and cache["state"] == state and cache["now"] <= now < cache["until"]:
                return cache, True
            health = self.tools.call("guarantee_health", {})
            impacts = self.client.named("guarantee_impact", {"guarantees": [g["id"] for g in health["guarantees"]]})
            tiers = {r["guarantee"]: min(r["tiers"]) if r["tiers"] else None for r in impacts}
            boundaries = [value for a in health["assumptions"] for att in a["attestations"]
                          for value in (att.get("on"), att["review_by"] + 1 if att.get("review_by") is not None else None)
                          if value is not None and value > now]
            cache = {"state": state, "now": health["now_ms"], "until": min(boundaries, default=float("inf")),
                     "guarantees": {g["id"]: {**g, "tier": tiers.get(g["id"])} for g in health["guarantees"]},
                     "assumptions": {a["id"]: a for a in health["assumptions"]}}
            self._cache = cache
            return cache, False

    @staticmethod
    def _ranks(health):
        return [{"id": g["id"], "score": g["pagerank"]} for g in health["guarantees"].values()]

    @staticmethod
    def _node(row, health):
        label = next(label for label in LABELS if label in row["labels"])
        g, a = health["guarantees"].get(row["id"]), health["assumptions"].get(row["id"])
        node = {"id": row["id"], "label": label,
                "title": row.get("title") or row.get("statement") or row.get("text") or row.get("name") or row["id"],
                "health": g["status"] if g else a["state"] if a else None,
                "tier": g["tier"] if g else row.get("tier"), "pagerank": g["pagerank"] if g else 0.0,
                "distance": row.get("distance", 0)}
        if row.get("status") is not None:
            node["lifecycle"] = row["status"]
        if label == "Fact":
            node["value"] = row.get("value")
        return node

    def _entity(self, id):
        rows = self.client.named("explore_entity", {"id": id, "labels": LABELS})
        if not rows:
            raise UnknownEntity(id)
        return rows[0]

    def _nodes(self, rows, health):
        return [self._node(row, health) for row in rows[:self.cap]]

    def _edges(self, nodes):
        return self.client.named("explore_edges", {"ids": [n["id"] for n in nodes]}) if nodes else []

    def overview(self, health):
        rows = self.client.named("explore_entities", {"labels": KINDS["reasoning"], "ids": None,
            "ranks": self._ranks(health), "limit": self.cap + 1})
        nodes = self._nodes(rows, health)
        return {"nodes": nodes, "edges": self._edges(nodes), "truncated": len(rows) > self.cap}

    def neighborhood(self, focus, depth, kinds, health):
        # Both FastAPI and this service validate before selecting a fixed query file.
        if type(depth) is not int or depth not in range(1, 5):
            raise ValueError("depth must be an integer from 1 to 4")
        selected = {kind.strip() for kind in kinds.split(",")}
        if not selected or not selected <= KINDS.keys():
            raise InvalidKinds()
        self._entity(focus)
        rows = self.client.named(f"explore_neighborhood_d{depth}", {
            "focus": focus, "labels": [label for key in KINDS if key in selected for label in KINDS[key]],
            "allowed_labels": LABELS, "ranks": self._ranks(health), "limit": self.cap + 1})
        nodes = self._nodes(rows, health)
        return {"nodes": nodes, "edges": self._edges(nodes), "truncated": len(rows) > self.cap}

    def path(self, from_id, to_id, health):
        self._entity(from_id)
        self._entity(to_id)
        rows = self.client.named("explore_path", {"from": from_id, "to": to_id, "labels": LABELS})
        if not rows or rows[0]["ids"] is None or not rows[0]["allowed"]:
            return {"nodes": [], "edges": [], "path": None, "truncated": False}
        path = rows[0]
        raw = self.client.named("explore_entities", {"ids": path["ids"], "labels": LABELS,
            "ranks": self._ranks(health), "limit": self.cap + 1})
        nodes = self._nodes(raw, health)
        # Keep paths atomic under a lowered test cap; don't suggest a partial path is complete.
        if len(raw) > self.cap:
            return {"nodes": nodes, "edges": self._edges(nodes), "path": None, "truncated": True}
        return {"nodes": nodes, "edges": path["edges"], "path": path["ids"], "truncated": False}

    def node(self, id, health):
        row = self._entity(id)
        node = self._node(row, health)
        details = {"node": node, "statement": node["title"], "health": node["health"],
                   "chain": deepcopy(health["guarantees"].get(id, {}).get("chain", [])),
                   "evidence": provenance(self.client, [id]), "owners": [], "reviewers": []}
        services = [id] if node["label"] == "Service" else [r["id"] for r in self.client.named("explore_services", {"id": id})]
        for service in services:
            details["owners"].extend(self.tools.call("who_knows", {"id": service}))
        decisions = [id] if node["label"] == "Decision" else []
        if node["label"] in {"Guarantee", "Assumption"}:
            gids = [id] if node["label"] == "Guarantee" else [g["id"] for g in health["guarantees"].values() if id in g["prerequisites"]]
            decisions = [r["id"] for r in self.client.named("explore_decisions", {"ids": gids})]
        lineages = [self.tools.call("decision_lineage", {"id": decision}) for decision in decisions]
        details["reviewers"] = sorted({reviewer for lineage in lineages for reviewer in lineage["reviewers"]})
        details["lineage"] = lineages
        if node["label"] == "Assumption":
            details["assumption"] = deepcopy(health["assumptions"].get(id))
        return {"nodes": [node], "edges": [], "truncated": False, **details}

    def execute(self, action):
        with QueryRecorder(self.client) as recorder:
            state = None
            try:
                state = self._state()
                health, hit = self._health(state)
                result = action(health)
                if self._state() != state:
                    raise GraphUnavailable("graph revision changed during exploration; retry")
                return {"graph_rev": state[0], **result, "queries": recorder.entries,
                        "health_cache": {"hit": hit, "graph_rev": state[0], "evaluated_at_ms": health["now"]}}
            except (UnknownEntity, InvalidKinds, GraphUnavailable) as exc:
                status, error = ((404, "unknown_entity") if isinstance(exc, UnknownEntity) else
                                 (422, "invalid_kinds") if isinstance(exc, InvalidKinds) else (503, "graph_not_ready"))
                return JSONResponse({"error": error, "graph_rev": state[0] if state else None,
                    "nodes": [], "edges": [], "truncated": False, "queries": recorder.entries}, status_code=status)


def create_graph_router(client, at_ms=None, node_cap=300):
    router = APIRouter(prefix="/api/graph", tags=["graph"], route_class=GraphRoute)
    explorer = GraphExplorer(client, at_ms=at_ms, node_cap=node_cap)

    @router.get("/overview")
    def overview():
        return explorer.execute(explorer.overview)

    @router.get('/facts')
    def facts():
        from .app import scenario_presets
        def collect(health):
            rows, presets = scenario_presets(client)
            links = client.read('MATCH (a:Assumption)-[:LHS|RHS]->(f:Fact) RETURN a.id AS assumption, f.id AS fact')
            for row in rows:
                row['assumptions'] = sorted(r['assumption'] for r in links if r['fact'] == row['id'])
            return {'nodes': [], 'edges': [], 'truncated': False, 'facts': rows, 'presets': presets}
        return explorer.execute(collect)

    @router.get("/neighborhood")
    def neighborhood(focus: str = Query(min_length=1, max_length=160), depth: int = Query(1, ge=1, le=4),
                     kinds: str = Query("reasoning,people,services,facts", max_length=100)):
        return explorer.execute(lambda health: explorer.neighborhood(focus, depth, kinds, health))

    @router.get("/path")
    def path(from_id: str = Query(alias="from", min_length=1, max_length=160),
             to_id: str = Query(alias="to", min_length=1, max_length=160)):
        return explorer.execute(lambda health: explorer.path(from_id, to_id, health))

    @router.get("/node/{id}")
    def node(id: str = Path(min_length=1, max_length=160)):
        return explorer.execute(lambda health: explorer.node(id, health))

    return router
