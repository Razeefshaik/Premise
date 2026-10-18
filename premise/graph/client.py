"""Thin wrapper over the official FalkorDB client. Every graph read or write in Premise goes through here.

The connection is opened lazily and every connection or timeout failure surfaces as GraphUnavailable, so an outage at
any moment (before or during an assessment) becomes an ERROR verdict instead of a crash.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from falkordb import FalkorDB
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.exceptions import ResponseError as RedisResponseError

QUERY_DIR = Path(__file__).parent / "queries"
_OUTAGE = (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError, OSError)


@lru_cache(maxsize=None)
def query_text(name: str) -> str:
    """Load a named Cypher query from premise/graph/queries/<name>.cypher."""
    return (QUERY_DIR / f"{name}.cypher").read_text()


class GraphUnavailable(RuntimeError):
    """FalkorDB cannot be reached or the graph is not in a usable state."""


class GraphClient:
    def __init__(self, host: str = "localhost", port: int = 6379, graph_name: str = "premise_kestrel", **connection_options):
        self.host, self.port, self.graph_name = host, port, graph_name
        self._connection_options = dict(connection_options)
        self._g = None

    @classmethod
    def from_settings(cls, config, *, host=None, port=None, graph_name=None):
        return cls(host or config.falkordb_host, port or config.falkordb_port,
                   graph_name or config.graph_name, **config.database_options)

    def sibling(self, graph_name):
        """A separate graph on the same authenticated, TLS-verified connection settings."""
        return GraphClient(self.host, self.port, graph_name, **self._connection_options)

    @property
    def graph(self):
        if self._g is None:
            try:
                db = FalkorDB(host=self.host, port=self.port, socket_timeout=5, socket_connect_timeout=2,
                              **self._connection_options)
                self._g = db.select_graph(self.graph_name)
            except _OUTAGE as exc:
                raise GraphUnavailable(str(exc)) from exc
        return self._g

    @staticmethod
    def _to_dicts(result) -> list[dict[str, Any]]:
        names = [h[1] for h in result.header]
        return [dict(zip(names, row)) for row in result.result_set]

    def write(self, cypher: str, params: dict | None = None) -> list[dict[str, Any]]:
        from ..public_demo import read_only_request, PublicDemoDisabled
        if read_only_request.get():
            raise PublicDemoDisabled()
        try:
            return self._to_dicts(self.graph.query(cypher, params or {}))
        except _OUTAGE as exc:
            raise GraphUnavailable(str(exc)) from exc

    def read(self, cypher: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Read only query (GRAPH.RO_QUERY): FalkorDB rejects any write inside it."""
        try:
            return self._to_dicts(self.graph.ro_query(cypher, params or {}))
        except _OUTAGE as exc:
            raise GraphUnavailable(str(exc)) from exc
        except RedisResponseError as exc:
            # RO_QUERY cannot create a missing graph. This is an expected fresh-start
            # condition, unlike a malformed query or other unexpected server error.
            if str(exc) == "Invalid graph operation on empty key":
                raise GraphUnavailable("Graph has not been initialized") from exc
            raise

    def named(self, name: str, params: dict | None = None) -> list[dict[str, Any]]:
        if name in {'evaluate_assumptions', 'route_decision'}:
            params = {'gone': [], **(params or {})}
        return self.read(query_text(name), params)

    def delete_graph(self) -> None:
        from ..public_demo import read_only_request, PublicDemoDisabled
        if read_only_request.get():
            raise PublicDemoDisabled()
        try:
            self.graph.delete()
        except Exception:
            pass
