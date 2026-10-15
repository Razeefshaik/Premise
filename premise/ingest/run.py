"""Ingest a checkout of the company repository into a graph revision."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..graph.client import GraphClient
from .load import load, mark_failed
from .parse import parse_repo
from .validate import validate


class IngestionError(RuntimeError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class IngestResult:
    rev: int
    warnings: list[str]
    node_count: int
    edge_count: int


def ingest(client: GraphClient, root: str | Path, commit_sha: str = "local", repo_url: str | None = None) -> IngestResult:
    model = parse_repo(Path(root), commit_sha, repo_url)
    errors, warnings = validate(model)
    if errors:
        mark_failed(client, errors)
        raise IngestionError(errors)
    rev = load(client, model, warnings, commit_sha)
    counts = client.read("MATCH (n:Entity) WHERE n.retired_rev IS NULL RETURN count(n) AS n")[0]["n"]
    edges = client.read("MATCH ()-[r]->() WHERE type(r) IN $t RETURN count(r) AS n",
                        {"t": list(model.edges.keys())})[0]["n"]
    return IngestResult(rev=rev, warnings=warnings, node_count=counts, edge_count=edges)
