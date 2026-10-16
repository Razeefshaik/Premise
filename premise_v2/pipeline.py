"""Phase 1 pipeline: collect -> stream -> gateway -> normalize -> extract -> ground -> stage -> reconcile -> propose.

Plane rule: this module writes only to the Redis stream and the STAGING graph. The decision graph is
read through RO queries (and, at setup, loaded by v1's own deterministic ingest from the model repo).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import redis

from premise.graph.client import GraphClient
from premise.ingest.run import ingest

from .envelope import Envelope
from .extract import FactClaimExtractor, body_of, ground
from .gateway import Gateway
from .normalize import IdentityResolver, to_kif
from .propose import ProposalWriter
from .reconcile import reconcile
from .registry import Ext, check_relations
from .staging import Staging
from .stream import EnvelopeStream
from .workers import JiraFixtureWorker, SlackFixtureWorker

EXTRACT_CLASSES = {"chat", "ticket", "ticket_comment", "doc"}


@dataclass
class RunSummary:
    produced: dict = field(default_factory=dict)
    tombstones: int = 0
    stream: dict = field(default_factory=dict)
    gateway: dict = field(default_factory=dict)
    redactions: int = 0
    claims: dict = field(default_factory=dict)
    rejected_by_grounding: list = field(default_factory=list)
    drifts: list = field(default_factory=list)
    confirmations: int = 0
    proposals: list = field(default_factory=list)
    registry_errors: list = field(default_factory=list)


def fixture_workers(fixtures: str | Path) -> list:
    root = Path(fixtures)
    workers = [SlackFixtureWorker(p) for p in sorted((root / "slack").glob("*.json"))]
    workers += [JiraFixtureWorker(p) for p in sorted((root / "jira").glob("*.json"))]
    return workers


class Pipeline:
    def __init__(self, r: redis.Redis, staging: GraphClient, decision: GraphClient, model_root: str | Path,
                 workers: list, out_dir: str | Path | None = None, github=None, model_prefix: str = "",
                 stream_name: str = "premise:v2:raw"):
        self.model_root = Path(model_root)
        self.ext = Ext.load(self.model_root)
        self.staging = Staging(staging)
        self.decision = decision
        self.stream = EnvelopeStream(r, stream=stream_name, dead=f"{stream_name}:dead", failures=f"{stream_name}:failures")
        self.workers = workers
        self.gateway = Gateway(self.ext, self.staging)
        self.resolver = IdentityResolver(self.ext)
        self.extractor = FactClaimExtractor(self.ext)
        self.writer = ProposalWriter(self.staging, decision, self.model_root, out_dir, github, model_prefix=model_prefix)
        self.summary = RunSummary()

    # ---- stages ------------------------------------------------------------------------------------
    def load_decision_graph(self, commit_sha: str = "local") -> None:
        """v1's deterministic ingest of the model repo into v2's own decision graph."""
        ingest(self.decision, self.model_root, commit_sha)

    def collect(self) -> None:
        for w in self.workers:
            source = w.name
            gen = w.fetch(self.staging.cursor(source))
            n = 0
            while True:
                try:
                    env = next(gen)
                except StopIteration as done:
                    new_cursor = done.value
                    break
                self.stream.produce(env)
                n += 1
            # Tombstones: items we hold that the source no longer lists.
            gone = self.staging.live_keys(source) - w.list_keys()
            for key in sorted(gone):
                latest = self.staging.latest_version(key) or {"sequence": 0}
                native = key.split(":", 1)[1]
                item = self.staging.item(key) or {}
                self.stream.produce(Envelope(entity_key=key, source=source, kind=item.get("kind", "message"),
                                             native_id=native, sequence=latest["sequence"] + 1, op="delete",
                                             time=datetime.now(timezone.utc)))
                self.summary.tombstones += 1
            # The cursor is saved only after every envelope is in the stream.
            self.staging.save_cursor(source, new_cursor)
            self.summary.produced[source] = self.summary.produced.get(source, 0) + n

    def handle(self, env: Envelope) -> None:
        res = self.gateway.process(env)
        self.summary.gateway[res.action] = self.summary.gateway.get(res.action, 0) + 1
        if res.action in {"duplicate", "stale"}:
            return
        if res.action == "deleted":
            self.staging.tombstone(env)
            return
        clean = res.envelope
        link = self.resolver.resolve(clean)
        self.summary.redactions += sum(res.redactions.values())
        self.staging.store_item(clean, cls=res.cls, in_scope=res.in_scope, person=link.person, link_method=link.method,
                                redactions=res.redactions, kif=to_kif(clean, res.cls, link.person))
        self.staging.retract_claims(clean.entity_key, "superseded_by_edit", below_sequence=clean.sequence)
        if res.in_scope and res.cls in EXTRACT_CLASSES:
            claims, _ = self.extractor.extract(clean, link.person)
            body = body_of(clean)
            for c in claims:
                ok, why = ground(c, body, self.ext)
                self.staging.add_claim(c, ok, why)
                self.summary.claims[c.status] = self.summary.claims.get(c.status, 0) + 1
                if not ok:
                    self.summary.rejected_by_grounding.append({"claim": c.id, "reason": why})
        self.staging.mark_processed(clean.entity_key, clean.sequence)

    def run(self, *, load_decision: bool = True, consumer: str = "gateway-1") -> RunSummary:
        self.summary.registry_errors = check_relations(self.ext.relations)
        if self.summary.registry_errors:
            return self.summary          # never run on a registry that breaks the Kind 1 lock
        self.staging.setup()
        if load_decision:
            self.load_decision_graph()
        self.collect()
        stats = self.stream.consume(consumer, self.handle)
        self.summary.stream = asdict(stats)
        self.writer.sync_outcomes()
        drifts, confirmations = reconcile(self.staging, self.decision, self.model_root)
        self.summary.confirmations = len(confirmations)
        for d in drifts:
            p = self.writer.write(d)
            self.summary.drifts.append({"fact": d.fact, "from": d.model_value, "to": d.value, "support": d.support,
                                        "contested": d.contested, "origins": d.origins,
                                        "supporting": len(d.supporting), "disagreeing": len(d.disagreeing),
                                        "weak": len(d.weak), "as_of_unknown": d.as_of_unknown})
            self.summary.proposals.append({"key": p.key, "branch": p.branch, "state": p.state, "reason": p.reason,
                                           "verdict_preview": p.preview.get("verdict"), "pr_url": p.pr_url})
        return self.summary
