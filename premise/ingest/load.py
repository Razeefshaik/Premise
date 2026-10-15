"""Load a parsed and validated model into FalkorDB as a new revision.

Order: mark ingesting, MERGE nodes and edges stamped with the revision, sweep authored edges from older revisions,
retire nodes not seen in this revision, then mark ready. Assessments refuse to run unless the state is ready.
"""
from __future__ import annotations

import json
from typing import Any

from ..graph.client import GraphClient
from .parse import AUTHORED_EDGE_TYPES, Model

LABELS = ("Person", "Team", "Service", "Decision", "Guarantee", "Assumption", "Fact", "Source", "Passage")
INDEXED_LABELS = LABELS + ("ChangeProposal", "Assessment", "Action")


def ensure_indexes(client: GraphClient) -> None:
    existing = {(r["label"], tuple(r["properties"]) if isinstance(r["properties"], list) else r["properties"])
                for r in client.write("CALL db.indexes() YIELD label, properties RETURN label, properties")}
    wanted = [("Entity", "id")] + [(label, "id") for label in INDEXED_LABELS]
    for label, prop in wanted:
        if (label, (prop,)) not in existing and (label, prop) not in existing:
            try:
                client.write(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            except Exception as exc:  # already exists in another form
                if "already" not in str(exc).lower():
                    raise
    for label, prop in (("Entity", "search_text"), ("Passage", "text")):
        try:
            client.write(f"CREATE FULLTEXT INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception as exc:
            if "already" not in str(exc).lower():
                raise


def _chunks(rows: list[Any], size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def load(client: GraphClient, model: Model, warnings: list[str], commit_sha: str) -> int:
    state = client.write("OPTIONAL MATCH (s:GraphState {id: 'state'}) RETURN s.rev AS rev")
    rev = (state[0]["rev"] or 0) + 1 if state else 1
    client.write("MERGE (s:GraphState {id: 'state'}) SET s.ingest_state = 'ingesting', s.ingesting_rev = $rev",
                 {"rev": rev})
    ensure_indexes(client)

    for label in LABELS:
        rows = [{"id": i, "props": {k: v for k, v in p.items() if v is not None}} for i, p in model.nodes[label].items()]
        for chunk in _chunks(rows):
            client.write(
                f"UNWIND $rows AS row MERGE (n:Entity:{label} {{id: row.id}}) "
                "SET n += row.props, n.seen_rev = $rev REMOVE n.retired_rev",
                {"rows": chunk, "rev": rev},
            )

    for type_ in AUTHORED_EDGE_TYPES:
        rows = [{"a": e["a"], "b": e["b"], "props": {k: v for k, v in e["props"].items() if v is not None}}
                for e in model.edges.get(type_, [])]
        for chunk in _chunks(rows):
            client.write(
                f"UNWIND $rows AS row MATCH (a:Entity {{id: row.a}}), (b:Entity {{id: row.b}}) "
                f"MERGE (a)-[r:{type_}]->(b) SET r += row.props, r.rev = $rev",
                {"rows": chunk, "rev": rev},
            )

    client.write(
        "MATCH ()-[r]->() WHERE type(r) IN $types AND r.rev < $rev DELETE r",
        {"types": list(AUTHORED_EDGE_TYPES), "rev": rev},
    )
    client.write("MATCH (n:Entity) WHERE n.seen_rev < $rev SET n.retired_rev = $rev", {"rev": rev})
    client.write(
        "MATCH (s:GraphState {id: 'state'}) SET s.rev = $rev, s.main_sha = $sha, s.ingest_state = 'ready', "
        "s.warnings_json = $warnings REMOVE s.ingesting_rev",
        {"rev": rev, "sha": commit_sha, "warnings": json.dumps(warnings)},
    )
    return rev


def mark_failed(client: GraphClient, errors: list[str]) -> None:
    client.write("MERGE (s:GraphState {id: 'state'}) SET s.ingest_state = 'failed', s.errors_json = $e",
                 {"e": json.dumps(errors)})
