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

    def store_item(self, env: Envelope, *, cls: str, in_scope: bool, person: str, link_method: str,
                   redactions: dict, kif: dict) -> None:
        self.c.write(
            "MERGE (i:Item {key:$key}) SET i.sequence=$seq, i.hash=$hash, i.deleted=false, i.source=$source, "
            "i.kind=$kind, i.url=$url, i.time_ms=$time, i.title=$title, i.text=$text, i.thread=$thread, "
            "i.container=$container, i.visibility=$vis, i.cls=$cls, i.in_scope=$scope, i.person=$person, "
            "i.link_method=$method, i.redactions_json=$red, i.kif_json=$kif, i.updated_ms=$now",
            {"key": env.entity_key, "seq": env.sequence, "hash": env.content_hash, "source": env.source,
             "kind": env.kind, "url": env.url, "time": int(env.time.timestamp() * 1000), "title": env.title,
             "text": env.text, "thread": env.thread, "container": env.container, "vis": env.visibility,
             "cls": cls, "scope": in_scope, "person": person, "method": link_method,
             "red": json.dumps(redactions), "kif": json.dumps(kif), "now": now_ms()})

    def tombstone(self, env: Envelope) -> None:
        self.c.write("MERGE (i:Item {key:$k}) SET i.deleted=true, i.sequence=$seq, i.hash=$hash, i.text='', "
                     "i.updated_ms=$now, i.processed_seq=$seq", {"k": env.entity_key, "seq": env.sequence, "hash": env.content_hash, "now": now_ms()})
        self.retract_claims(env.entity_key, "source_deleted")

    def live_keys(self, source: str) -> set[str]:
        rows = self.c.read("MATCH (i:Item) WHERE i.source=$s AND NOT i.deleted RETURN i.key AS k", {"s": source})
        return {r["k"] for r in rows}

    def item(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (i:Item {key:$k}) RETURN properties(i) AS p", {"k": key})
        return rows[0]["p"] if rows else None

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

    # ---- proposals and rejection memory ------------------------------------------------------------
    def proposal(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (p:Proposal {key:$k}) RETURN properties(p) AS p", {"k": key})
        return rows[0]["p"] if rows else None

    def upsert_proposal(self, key: str, props: dict) -> None:
        self.c.write("MERGE (p:Proposal {key:$k}) ON CREATE SET p.created_ms=$now SET p += $p, p.updated_ms=$now",
                     {"k": key, "p": props, "now": now_ms()})

    def reject(self, key: str, fact: str, value, reason: str, at_ms: int | None = None) -> None:
        self.c.write("MERGE (r:Rejection {key:$k}) SET r.fact=$f, r.value=$v, r.reason=$why, r.at_ms=$at",
                     {"k": key, "f": fact, "v": value, "why": reason, "at": at_ms or now_ms()})

    def rejection(self, key: str) -> dict | None:
        rows = self.c.read("MATCH (r:Rejection {key:$k}) RETURN properties(r) AS r", {"k": key})
        return rows[0]["r"] if rows else None
