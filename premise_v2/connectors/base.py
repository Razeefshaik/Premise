from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Generator, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from ..envelope import Envelope


class ConnectorFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str
    native_id: str | None = None
    error: str
    retryable: bool = True


@runtime_checkable
class Connector(Protocol):
    name: str
    scope: str

    def load(self, checkpoint: dict | None) -> Generator[Envelope | ConnectorFailure, None, dict]: ...
    def list_keys(self) -> set[str]: ...


def timestamp(value) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("source timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def load_fixture(worker, checkpoint):
    """Adapt the Phase 1 parsers, isolating errors to a source record and preserving fetch()."""
    cursor = (checkpoint or {}).get("cursor")
    high = cursor
    seen = set()
    try:
        if worker.name == "slack":
            channel, users, rows = worker._load()
            snapshots = [(str(row.get("ts", "unknown")), (channel, users, [row])) for row in rows]
        else:
            snapshots = [(str(row.get("key", "unknown")), [row]) for row in worker._issues()]
    except (OSError, ValueError, KeyError, TypeError):
        yield ConnectorFailure(scope=worker.scope, error="cannot read fixture snapshot")
        return checkpoint or {}
    for native, snapshot in snapshots:
        isolated = copy.copy(worker)
        if worker.name == "slack":
            isolated._load = lambda snapshot=snapshot: snapshot
        else:
            isolated._issues = lambda snapshot=snapshot: snapshot
        gen = isolated.fetch(cursor)
        try:
            while True:
                try:
                    env = next(gen)
                except StopIteration as done:
                    if done.value is not None:
                        high = max(str(high or ""), str(done.value))
                    break
                if env.entity_key not in seen:
                    seen.add(env.entity_key)
                    yield env
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            yield ConnectorFailure(scope=worker.scope, native_id=native, error=f"invalid fixture record ({type(exc).__name__})")
    return {"cursor": high} if high is not None else (checkpoint or {})
