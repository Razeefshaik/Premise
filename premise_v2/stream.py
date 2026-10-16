"""Redis Streams on the FalkorDB server: at-least-once delivery with idempotent consumers.

Guardrails from the research:
1. On start, a consumer first re-reads its own pending entries (it may have crashed mid-batch).
2. Entries idle in another consumer's pending list are claimed with XAUTOCLAIM.
3. Failures are counted per entry; after ``max_failures`` the entry goes to the dead letter stream.
4. Entries are acknowledged only after the handler has committed its result. No trimming in Phase 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import redis
from pydantic import ValidationError

from .envelope import Envelope

RAW = "premise:v2:raw"
DEAD = "premise:v2:dead"
FAILURES = "premise:v2:failures"


@dataclass
class ConsumeStats:
    processed: int = 0
    failed: int = 0
    dead: int = 0
    reclaimed: int = 0
    pending_after: int = 0
    errors: list[str] = field(default_factory=list)


class EnvelopeStream:
    def __init__(self, r: redis.Redis, stream: str = RAW, group: str = "gateway", dead: str = DEAD,
                 failures: str = FAILURES):
        self.r, self.stream, self.group, self.dead, self.failures = r, stream, group, dead, failures

    def ensure_group(self) -> None:
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def produce(self, env: Envelope) -> str:
        return self.r.xadd(self.stream, {"envelope": env.to_json()})

    def _batches(self, consumer: str, count: int, min_idle_ms: int, stats: ConsumeStats):
        after = "0"
        while True:
            own = self.r.xreadgroup(self.group, consumer, {self.stream: after}, count=count)
            if not own or not own[0][1]:
                break
            after = own[0][1][-1][0]
            yield [e for e in own[0][1] if e[1]]
        cursor = "0-0"
        while True:
            cursor, claimed, *_ = self.r.xautoclaim(self.stream, self.group, consumer, min_idle_ms, cursor, count=count)
            claimed = [e for e in claimed if e and e[1]]
            if claimed:
                stats.reclaimed += len(claimed)
                yield claimed
            if cursor in ("0-0", b"0-0"):
                break
        while True:
            fresh = self.r.xreadgroup(self.group, consumer, {self.stream: ">"}, count=count)
            if not fresh or not fresh[0][1]:
                return
            yield fresh[0][1]

    def consume(self, consumer: str, handler: Callable[[Envelope], object], *, count: int = 100,
                min_idle_ms: int = 60_000, max_failures: int = 3) -> ConsumeStats:
        self.ensure_group()
        stats = ConsumeStats()
        tried = set()
        for batch in self._batches(consumer, count, min_idle_ms, stats):
            for entry_id, fields in batch:
                if entry_id in tried:
                    continue
                tried.add(entry_id)
                raw = fields.get(b"envelope") or fields.get("envelope")
                try:
                    env = Envelope.from_json(raw)
                except (ValidationError, TypeError, ValueError) as exc:
                    self._dead(entry_id, raw, f"invalid envelope: {type(exc).__name__}", stats)
                    continue
                try:
                    handler(env)
                except Exception as exc:  # retried later; poison entries end in the dead letter stream
                    n = self.r.hincrby(self.failures, entry_id, 1)
                    stats.failed += 1
                    stats.errors.append(f"{env.entity_key}: {type(exc).__name__}: {exc}")
                    if n >= max_failures:
                        self._dead(entry_id, raw, f"handler failed {n} times: {type(exc).__name__}", stats)
                    continue
                self.r.xack(self.stream, self.group, entry_id)
                self.r.hdel(self.failures, entry_id)
                stats.processed += 1
        stats.pending_after = self.pending()
        return stats

    def _dead(self, entry_id, raw, reason: str, stats: ConsumeStats) -> None:
        self.r.xadd(self.dead, {"envelope": raw or b"", "reason": reason, "entry": entry_id})
        self.r.xack(self.stream, self.group, entry_id)
        self.r.hdel(self.failures, entry_id)
        stats.dead += 1

    def pending(self) -> int:
        try:
            return self.r.xpending(self.stream, self.group)["pending"]
        except redis.ResponseError:
            return 0
