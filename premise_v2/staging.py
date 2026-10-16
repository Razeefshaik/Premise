"""Staging graph: the evidence plane. A separate FalkorDB graph that verdict code never reads.

Nodes:  Item (one per entity_key, latest version), Claim, Proposal, Rejection, Cursor
Edges:  (Claim)-[:CITES {quote, start, end}]->(Item)
"""
from __future__ import annotations

import json
import time

from premise.graph.client import GraphClient

from .envelope import Envelope
from .extract import Claim


def now_ms() -> int:
    return int(time.time() * 1000)


class Staging:
    def __init__(self, client: GraphClient):
        self.c = client

    def setup(self) -> None:
        for label, prop in (("Item", "key"), ("Claim", "id"), ("Proposal", "key"), ("Rejection", "key"), ("Cursor", "source")):
            try:
                self.c.write(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            except Exception as exc:  # already exists
                if "already indexed" not in str(exc).lower() and "already exists" not in str(exc).lower():
                    raise

    # ---- items -------------------------------------------------------------------------------------
    def latest_version(self, key: str) -> dict | None:
        rows = self.c.write("MATCH (i:Item {key:$k}) RETURN i.sequence AS sequence, i.hash AS hash, i.deleted AS deleted, "
                          "i.processed_seq AS processed", {"k": key})
        if not rows:
            return None
        r = rows[0]
        return {"sequence": r["sequence"], "hash": r["hash"], "deleted": bool(r["deleted"]),
                "processed": r["processed"] == r["sequence"]}

    def mark_processed(self, key: str, sequence: int) -> None:
        """Set only after claims are stored, so a crash between the two steps is retried, not skipped."""
        self.c.write("MATCH (i:Item {key:$k}) SET i.processed_seq=$s", {"k": key, "s": sequence})

    def advance_version(self, key: str, sequence: int) -> None:
        self.c.write("MATCH (i:Item {key:$k}) WHERE i.sequence < $s SET i.sequence=$s, i.processed_seq=$s",
                     {"k": key, "s": sequence})

    def store_item(self, env: Envelope, *, cls: str, in_scope: bool, person: str, link_method: str,
                   redactions: dict, kif: dict) -> None:
        self.c.write(
            "MERGE (i:Item {key:$key}) SET i.sequence=$seq, i.hash=$hash, i.deleted=false, i.source=$source, "
            "i.kind=$kind, i.url=$url, i.time_ms=$time, i.title=$title, i.text=$text, i.thread=$thread, "
            "i.container=$container, i.visibility=$vis, i.cls=$cls, i.in_scope=$in_scope, i.scope=$scope, i.person=$person, "
            "i.link_method=$method, i.redactions_json=$red, i.kif_json=$kif, i.updated_ms=$now",
            {"key": env.entity_key, "seq": env.sequence, "hash": env.content_hash, "source": env.source,
             "kind": env.kind, "url": env.url, "time": int(env.time.timestamp() * 1000), "title": env.title,
             "text": env.text, "thread": env.thread, "container": env.container, "vis": env.visibility,
             "cls": cls, "in_scope": in_scope, "scope": env.scope, "person": person, "method": link_method,
             "red": json.dumps(redactions), "kif": json.dumps(kif), "now": now_ms()})

    def tombstone(self, env: Envelope) -> None:
        self.c.write("MERGE (i:Item {key:$k}) SET i.deleted=true, i.sequence=$seq, i.hash=$hash, i.text='', "
                     "i.scope=coalesce($scope, i.scope), i.updated_ms=$now, i.processed_seq=$seq",
                     {"k": env.entity_key, "seq": env.sequence, "hash": env.content_hash, "scope": env.scope, "now": now_ms()})
        self.retract_claims(env.entity_key, "source_deleted")
        self.c.write("MATCH (o:Ownership {item:$k}) DELETE o", {"k": env.entity_key})

    def live_keys(self, scope: str) -> set[str]:
        rows = self.c.read("MATCH (i:Item) WHERE i.scope=$s AND NOT i.deleted RETURN i.key AS k", {"s": scope})
        return {r["k"] for r in rows}

    def adopt_scope(self, key: str, scope: str) -> None:
        """Backfill ownership when pre-scope evidence is replayed by its connector."""
        self.c.write("MATCH (i:Item {key:$k}) WHERE i.scope IS NULL SET i.scope=$s", {"k": key, "s": scope})

    def adopt_account(self, key: str, account: str) -> None:
        """Backfill replayed Phase 1 evidence without re-extracting unchanged text."""
        self.c.write("MATCH (i:Item {key:$k}) WHERE i.account IS NULL SET i.account=$a",
                     {"k": key, "a": account})
        self.c.write("MATCH (c:Claim {envelope_key:$k}) WHERE c.account IS NULL "
                     "SET c.account=$a REMOVE c.person", {"k": key, "a": account})

    def item(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (i:Item {key:$k}) RETURN properties(i) AS p", {"k": key})
        return rows[0]["p"] if rows else None

    def items(self) -> list[dict]:
        rows = self.c.read("MATCH (i:Item) WHERE NOT i.deleted RETURN properties(i) AS p ORDER BY i.key")
        items = []
        for row in rows:
            item = dict(row["p"])
            item["body"] = f"{item['title']}\n{item['text']}" if item.get("title") else item.get("text", "")
            item["account"] = item.get("account") or item.get("person")
            items.append(item)
        return items

    def extractions(self, extractor: str) -> list[dict]:
        rows = self.c.read("MATCH (e:Extraction)-[:CITES]->(i:Item) WHERE e.extractor=$name AND e.grounded "
                           "AND NOT i.deleted AND e.sequence=i.sequence RETURN properties(e) AS e, properties(i) AS i",
                           {"name": extractor})
        out = []
        for row in rows:
            c = dict(row["e"])
            item = row["i"]
            c.update(data=json.loads(c["data_json"]), envelope_key=item["key"], item_thread=item.get("thread"),
                     item_text=(f"{item['title']}\n" if item.get("title") else "") + item.get("text", ""),
                     source=item.get("source"), container=item.get("container"), visibility=item.get("visibility"), url=item.get("url"))
            out.append(c)
        return out

    def upsert_review(self, key: str, kind: str, title: str, data: dict, status="open") -> None:
        self.c.write("MERGE (r:ReviewItem {key:$k}) ON CREATE SET r.created_ms=$now "
                     "SET r.kind=$kind, r.title=$title, r.data_json=$data, r.status=$status, r.updated_ms=$now",
                     {"k": key, "kind": kind, "title": title, "data": json.dumps(data), "status": status, "now": now_ms()})

    def review_items(self, kind: str | None = None, status: str = "open") -> list[dict]:
        rows = self.c.read("MATCH (r:ReviewItem) WHERE r.status=$status AND ($kind IS NULL OR r.kind=$kind) "
                           "RETURN properties(r) AS r ORDER BY r.key", {"kind": kind, "status": status})
        return [dict(row["r"], data=json.loads(row["r"]["data_json"])) for row in rows]

    # ---- claims ------------------------------------------------------------------------------------
    def retract_claims(self, key: str, reason: str, below_sequence: int | None = None) -> None:
        self.c.write("MATCH (c:Claim {envelope_key:$k}) WHERE c.retracted IS NULL AND ($seq IS NULL OR c.sequence < $seq) "
                     "SET c.retracted=$why", {"k": key, "seq": below_sequence, "why": reason})

    def add_claim(self, claim: Claim, grounded: bool, reason: str) -> None:
        props = {k: v for k, v in claim.to_props().items() if v is not None}
        props.update(grounded=grounded, grounding=reason)
        self.c.write("MATCH (i:Item {key:$key}) MERGE (c:Claim {id:$id}) SET c += $p "
                     "MERGE (c)-[r:CITES]->(i) SET r.quote=$quote, r.start=$start, r.end=$end",
                     {"key": claim.envelope_key, "id": claim.id, "p": props, "quote": claim.quote,
                      "start": claim.start, "end": claim.end})

    def active_claims(self) -> list[dict]:
        rows = self.c.read("MATCH (c:Claim)-[:CITES]->(i:Item) WHERE c.retracted IS NULL AND c.grounded AND NOT i.deleted "
                           "RETURN properties(c) AS c, i.key AS key, i.thread AS thread, i.text AS text, i.title AS title, "
                           "i.url AS url, i.source AS source, i.container AS container, i.visibility AS visibility "
                           "ORDER BY c.as_of_ms, c.id")
        out = []
        for r in rows:
            c = dict(r["c"])
            c.update(item_thread=r["thread"], item_text=f"{r['title']}\n{r['text']}" if r["title"] else r["text"],
                     url=r["url"], source=r["source"], container=r["container"], visibility=r["visibility"])
            out.append(c)
        return out

    def claim_counts(self) -> dict:
        rows = self.c.read("MATCH (c:Claim) RETURN c.grounded AS g, c.retracted IS NULL AS live, c.status AS s, count(*) AS n")
        return [dict(r) for r in rows]

    # ---- cursors -----------------------------------------------------------------------------------
    def cursor(self, source: str) -> str | None:
        rows = self.c.read("MATCH (c:Cursor {source:$s}) RETURN c.value AS v", {"s": source})
        return rows[0]["v"] if rows else None

    def save_cursor(self, source: str, value: str | None) -> None:
        if value is not None:
            self.c.write("MERGE (c:Cursor {source:$s}) SET c.value=$v, c.updated_ms=$now", {"s": source, "v": value, "now": now_ms()})

    def checkpoint(self, scope: str) -> dict | None:
        raw = self.cursor(scope)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {"cursor": raw}
        except (ValueError, TypeError):
            return {"cursor": raw}

    def save_checkpoint(self, scope: str, value: dict) -> None:
        self.save_cursor(scope, json.dumps(value, sort_keys=True))

    def connector_failure(self, failure) -> None:
        key = f"{failure.scope}|{failure.native_id or '*'}"
        self.c.write("MERGE (f:ConnectorFailure {key:$k}) SET f.scope=$s, f.native_id=$id, f.error=$e, "
                     "f.retryable=$r, f.status='pending', f.updated_ms=$now",
                     {"k": key, "s": failure.scope, "id": failure.native_id, "e": failure.error,
                      "r": failure.retryable, "now": now_ms()})

    def connector_recovered(self, scope: str) -> None:
        self.c.write("MATCH (f:ConnectorFailure {scope:$s}) SET f.status='resolved', f.updated_ms=$now",
                     {"s": scope, "now": now_ms()})

    def store_ownership(self, env: Envelope) -> None:
        """CODEOWNERS remains descriptive evidence, never a reasoning edge."""
        self.c.write("MATCH (o:Ownership {item:$k}) DELETE o", {"k": env.entity_key})
        for line in env.text.splitlines():
            parts = line.split('#', 1)[0].split()
            if len(parts) >= 2:
                self.c.write("CREATE (:Ownership {item:$k, pattern:$p, owners:$owners, visibility:$v})",
                             {"k": env.entity_key, "p": parts[0], "owners": parts[1:], "v": env.visibility})

    # ---- proposals and rejection memory ------------------------------------------------------------
    def proposal(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (p:Proposal {key:$k}) RETURN properties(p) AS p", {"k": key})
        return rows[0]["p"] if rows else None

    def proposals(self, status: str = "open") -> list[dict]:
        rows = self.c.read("MATCH (p:Proposal) WHERE p.status=$s RETURN properties(p) AS p", {"s": status})
        return [r["p"] for r in rows]

    def upsert_proposal(self, key: str, props: dict) -> None:
        self.c.write("MERGE (p:Proposal {key:$k}) ON CREATE SET p.created_ms=$now SET p += $p, p.updated_ms=$now",
                     {"k": key, "p": props, "now": now_ms()})

    def reject(self, key: str, fact: str, value, reason: str, at_ms: int | None = None) -> None:
        self.c.write("MERGE (r:Rejection {key:$k}) SET r.fact=$f, r.value=$v, r.reason=$why, r.at_ms=$at",
                     {"k": key, "f": fact, "v": value, "why": reason, "at": at_ms or now_ms()})

    def rejection(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (r:Rejection {key:$k}) RETURN properties(r) AS r", {"k": key})
        return rows[0]["r"] if rows else None
