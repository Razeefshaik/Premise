"""Operational memory in FalkorDB; domain facts are never changed by assessments."""
from __future__ import annotations

import hashlib
import json
from ..reasoning.models import AssessmentResult
from ..reasoning.assess import now_ms


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def assessment_id(result):
    return digest([result.pr, result.head_sha, result.graph_rev])[:24]


class Store:
    def __init__(self, client):
        self.client = client

    def save(self, result, pr):
        aid = assessment_id(result)
        pid = f"pr:{pr['number']}"
        self.client.write("MERGE (p:ChangeProposal {id:$id}) SET p += $props",
            {"id": pid, "props": {"pr_number": pr["number"], "title": pr["title"], "head_sha": pr["head"]["sha"],
            "head_ref": pr["head"]["ref"], "base_ref": pr["base"]["ref"], "state": pr["state"],
            "same_repo": pr["head"]["repo"]["full_name"].lower() == pr["base"]["repo"]["full_name"].lower(),
            "changed_paths": result.changed_paths}})
        self.client.write("MATCH (p:ChangeProposal {id:$id})-[r:CHANGES]->() DELETE r", {"id": pid})
        for c in result.changed_facts:
            self.client.write("MATCH (p:ChangeProposal {id:$id}), (f:Fact {id:$fact}) MERGE (p)-[r:CHANGES]->(f) "
                "SET r.from=$old, r.to=$new, r.deleted=$deleted",
                {"id": pid, "fact": c.fact, "old": c.old, "new": c.new, "deleted": c.deleted})
        self.client.write("MATCH (p:ChangeProposal {id:$pid}) MERGE (a:Assessment {id:$id}) SET a += $props MERGE (a)-[:OF]->(p)",
            {"pid": pid, "id": aid, "props": {"verdict": result.verdict, "graph_rev": result.graph_rev,
             "head_sha": result.head_sha, "created_at": now_ms(), "result_json": result.model_dump_json(),
             "reasons_json": json.dumps([r.model_dump() for r in result.reasons])}})
        self.client.write("MATCH (a:Assessment {id:$id})-[r:FOUND|FLAGGED]->() DELETE r", {"id": aid})
        for item in [*result.assumptions, *result.guarantees]:
            role = getattr(item, "state", getattr(item, "status", ""))
            if role in ("violated", "unevaluable", "unverified", "broken", "unknown"):
                self.client.write("MATCH (a:Assessment {id:$id}), (e:Entity {id:$entity}) MERGE (a)-[r:FOUND]->(e) SET r.role=$role",
                    {"id": aid, "entity": item.id, "role": role})
        for d in result.decisions:
            self.client.write("MATCH (a:Assessment {id:$id}), (d:Decision {id:$did}) MERGE (a)-[r:FLAGGED]->(d) SET r.roles=$roles",
                {"id": aid, "did": d.id, "roles": d.roles})
        return aid

    def get(self, aid):
        rows = self.client.read("MATCH (a:Assessment {id:$id}) RETURN a.result_json AS result", {"id": aid})
        return AssessmentResult.model_validate_json(rows[0]["result"]) if rows else None

    def recent(self, limit=20):
        return self.client.read("MATCH (a:Assessment)-[:OF]->(p:ChangeProposal) RETURN a.id AS id, a.verdict AS verdict, "
            "a.head_sha AS head_sha, a.graph_rev AS graph_rev, p.pr_number AS pr, p.title AS title, a.created_at AS created_at "
            "ORDER BY created_at DESC LIMIT $limit", {"limit": limit})

    def action(self, key):
        rows = self.client.read("MATCH (a:Action {id:$id}) RETURN properties(a) AS action", {"id": key})
        return rows[0]["action"] if rows else None

    def begin(self, key, kind, aid, payload):
        self.client.write("MATCH (s:Assessment {id:$aid}) MERGE (a:Action {id:$key}) "
            "SET a.idem_key=$key, a.kind=$kind, a.status='executing', a.payload_json=$payload, "
            "a.created_at=$now MERGE (s)-[:TOOK]->(a)",
            {"key": key, "kind": kind, "aid": aid, "payload": json.dumps(payload), "now": now_ms()})

    def finish(self, key, status="done", url="", error=""):
        self.client.write("MATCH (a:Action {id:$key}) SET a.status=$status, a.external_url=$url, a.error=$error",
            {"key": key, "status": status, "url": url, "error": error})

    def cursor(self):
        rows = self.client.read("MATCH (s:GraphState {id:'state'}) RETURN s.pr_cursor_json AS cursor")
        return json.loads(rows[0]["cursor"] or "{}") if rows else {}

    def set_cursor(self, cursor):
        self.client.write("MATCH (s:GraphState {id:'state'}) SET s.pr_cursor_json=$cursor", {"cursor": json.dumps(cursor)})
