"""Phase 1 pipeline: collect -> stream -> gateway -> normalize -> extract -> ground -> stage -> reconcile -> propose.

Plane rule: this module writes only to the Redis stream and the STAGING graph. The decision graph is
read through RO queries (and, at setup, loaded by v1's own deterministic ingest from the model repo).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json

import redis

from premise.graph.client import GraphClient
from premise.ingest.run import ingest

from .envelope import Envelope
from .extract import FactClaimExtractor, body_of, ground
from .gateway import Gateway
from .normalize import to_kif
from .identity import IdentityDirectory
from .extract.base import ExtractionRunner
from .extract.attestation import AttestationExtractor
from .challenges import ChallengeWriter
from .extract.knowledge import KnowledgeExtractor, KnowledgeModelExtractor
from .knowledge import KnowledgeWriter
from .propose import ProposalWriter
from .reconcile import reconcile
from .registry import Ext, check_relations
from .staging import Staging
from .stream import EnvelopeStream
from .workers import JiraFixtureWorker, SlackFixtureWorker
from .connectors import ConnectorFailure, GitHubConnector, PagesConnector

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
    withdrawals: list = field(default_factory=list)
    registry_errors: list = field(default_factory=list)
    caught_up: bool = True
    proposal_skip_reason: str = ""
    connector_failures: list = field(default_factory=list)
    identity_proposals: list = field(default_factory=list)
    extraction: dict = field(default_factory=dict)
    challenges: list = field(default_factory=list)
    knowledge_proposals: list = field(default_factory=list)


def fixture_workers(fixtures: str | Path) -> list:
    root = Path(fixtures)
    workers = [SlackFixtureWorker(p) for p in sorted((root / "slack").glob("*.json"))]
    workers += [JiraFixtureWorker(p) for p in sorted((root / "jira").glob("*.json"))]
    workers += [GitHubConnector(json.loads(p.read_text(encoding="utf-8"))["repository"]["full_name"], fixture=p)
                for p in sorted((root / "github").glob("*.json"))]
    if (root / "pages").is_dir():
        workers.append(PagesConnector(root / "pages"))
    return workers


class Pipeline:
    def __init__(self, r: redis.Redis, staging: GraphClient, decision: GraphClient, model_root: str | Path,
                 workers: list, out_dir: str | Path | None = None, github=None, model_prefix: str = "",
                 stream_name: str = "premise:v2:raw", adapter=None, llm_provider="none", model_budget=40, issue_github=None):
        self.model_root = Path(model_root)
        self.ext = Ext.load(self.model_root)
        self.staging = Staging(staging)
        self.decision = decision
        self.stream = EnvelopeStream(r, stream=stream_name, dead=f"{stream_name}:dead", failures=f"{stream_name}:failures")
        self.workers = workers
        self.gateway = Gateway(self.ext, self.staging)
        self.identities = IdentityDirectory(self.staging, decision, self.model_root)
        self.extractor = FactClaimExtractor(self.ext)
        self.writer = ProposalWriter(self.staging, decision, self.model_root, out_dir, github, model_prefix=model_prefix)
        self.summary = RunSummary()
        self.adapter, self.llm_provider, self.model_budget = adapter, llm_provider, model_budget
        self.issue_github = issue_github

    # ---- stages ------------------------------------------------------------------------------------
    def load_decision_graph(self, commit_sha: str = "local") -> None:
        """v1's deterministic ingest of the model repo into v2's own decision graph."""
        ingest(self.decision, self.model_root, commit_sha)

    def collect(self) -> None:
        for w in self.workers:
            source = w.name
            gen = w.load(self.staging.checkpoint(w.scope))
            n = 0
            failures = []
            while True:
                try:
                    env = next(gen)
                except StopIteration as done:
                    new_cursor = done.value
                    break
                if isinstance(env, ConnectorFailure):
                    self.staging.connector_failure(env)
                    failures.append(env)
                    self.summary.connector_failures.append(env.model_dump())
                    continue
                self.stream.produce(env)
                n += 1
            self.summary.produced[source] = self.summary.produced.get(source, 0) + n
            # A partial listing must never manufacture deletions. Retain the checkpoint
            # on retryable failures, replaying successful items safely next time.
            if failures:
                if not any(f.retryable for f in failures):
                    self.staging.save_checkpoint(w.scope, new_cursor)
                continue
            # Tombstones: items we hold that the source no longer lists.
            try:
                gone = self.staging.live_keys(w.scope) - w.list_keys()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                failure = ConnectorFailure(scope=w.scope, error=f"listing unavailable ({type(exc).__name__})")
                self.staging.connector_failure(failure)
                self.summary.connector_failures.append(failure.model_dump())
                continue
            for key in sorted(gone):
                latest = self.staging.latest_version(key) or {"sequence": 0}
                native = key.split(":", 1)[1]
                item = self.staging.item(key) or {}
                self.stream.produce(Envelope(entity_key=key, source=source, scope=w.scope, kind=item.get("kind", "message"),
                                             native_id=native, sequence=latest["sequence"] + 1, op="delete",
                                             time=datetime.now(timezone.utc)))
                self.summary.tombstones += 1
            # The cursor is saved only after every envelope is in the stream.
            self.staging.save_checkpoint(w.scope, new_cursor)
            self.staging.connector_recovered(w.scope)

    def handle(self, env: Envelope) -> None:
        res = self.gateway.process(env)
        self.summary.gateway[res.action] = self.summary.gateway.get(res.action, 0) + 1
        if res.action == "stale":
            return
        if res.action == "deleted":
            self.staging.tombstone(env)
            return
        account = self.identities.capture(res.envelope)
        if res.action == "duplicate" and env.scope:
            self.staging.adopt_scope(env.entity_key, env.scope)
        if res.action == "duplicate":
            return
        clean = res.envelope
        self.summary.redactions += sum(res.redactions.values())
        self.staging.store_item(clean, cls=res.cls, in_scope=res.in_scope, person=account, link_method="account",
                                redactions=res.redactions, kif=to_kif(clean, res.cls, account))
        self.staging.retract_claims(clean.entity_key, "superseded_by_edit", below_sequence=clean.sequence)
        if res.in_scope and res.cls in EXTRACT_CLASSES:
            claims, _ = self.extractor.extract(clean, account)
            body = body_of(clean)
            for c in claims:
                ok, why = ground(c, body, self.ext)
                self.staging.add_claim(c, ok, why)
                self.summary.claims[c.status] = self.summary.claims.get(c.status, 0) + 1
                if not ok:
                    self.summary.rejected_by_grounding.append({"claim": c.id, "reason": why})
        if clean.kind == "file" and clean.source == "github" and clean.native_id.endswith("CODEOWNERS"):
            self.staging.store_ownership(clean)
        self.staging.mark_processed(clean.entity_key, clean.sequence)

    def run(self, *, load_decision: bool = True, consumer: str = "gateway-1") -> RunSummary:
        self.summary = RunSummary()
        self.summary.registry_errors = check_relations(self.ext.relations)
        if self.summary.registry_errors:
            return self.summary          # never run on a registry that breaks the Kind 1 lock
        self.staging.setup()
        if load_decision:
            self.load_decision_graph()
        self.collect()
        stats = self.stream.consume(consumer, self.handle)
        self.summary.stream = asdict(stats)
        self.summary.caught_up = stats.pending_after == 0
        if not self.summary.caught_up:
            self.summary.proposal_skip_reason = "stream not caught up"
            return self.summary
        runner = ExtractionRunner(self.staging, [AttestationExtractor(self.decision), KnowledgeExtractor(self.decision, self.model_root),
                                               KnowledgeModelExtractor(self.decision, self.model_root)], self.adapter,
                                  self.llm_provider, self.model_budget)
        self.summary.extraction = runner.run(self.staging.items())
        challenges = ChallengeWriter(self.staging, self.decision, self.model_root, self.writer.out, self.issue_github).run()
        self.summary.challenges = [{k: c[k] for k in ("key", "assumption", "support", "contested", "origins", "reviewers", "issue_url") if k in c}
                                   for c in challenges]
        self.writer.sync_outcomes()
        drifts, confirmations = reconcile(self.staging, self.decision, self.model_root)
        self.summary.confirmations = len(confirmations)
        current = set()
        by_key = {d.key_id: d for d in drifts}
        for old in self.staging.review_items("drift"):
            if old["key"] not in by_key:
                self.staging.upsert_review(old["key"], "drift", old["title"], old["data"], "withdrawn")
        for d in drifts:
            self.staging.upsert_review(d.key_id, "drift", f"Review {d.fact}: {d.value} {d.unit}",
                {"support": d.support, "contested": d.contested, "origins": d.origins,
                 "evidence": d.supporting + d.disagreeing + d.weak})
            p = self.writer.write(d)
            if p.state in {"created", "updated", "unchanged"}:
                current.add(p.key)
            self.summary.drifts.append({"fact": d.fact, "from": d.model_value, "to": d.value, "support": d.support,
                                        "contested": d.contested, "origins": d.origins,
                                        "supporting": len(d.supporting), "disagreeing": len(d.disagreeing),
                                        "weak": len(d.weak), "as_of_unknown": d.as_of_unknown})
            self.summary.proposals.append({"key": p.key, "branch": p.branch, "state": p.state, "reason": p.reason,
                                           "verdict_preview": p.preview.get("verdict"), "pr_url": p.pr_url})
        for existing in self.staging.proposals():
            if existing.get("kind", "drift") != "drift":
                continue
            if existing["key"] in current:
                continue
            d = by_key.get(existing["key"])
            reason = "no remaining evidence" if d is None else (
                "evidence now has only one independent origin" if d.support == "observed"
                else "evidence no longer supports a valid model update")
            withdrawn = self.writer.withdraw(existing["key"], reason)
            if withdrawn:
                self.summary.withdrawals.append(withdrawn)
        self.summary.identity_proposals = self.identities.propose(self.writer)
        self.summary.knowledge_proposals = KnowledgeWriter(self.staging, self.decision, self.model_root, self.writer).run()
        return self.summary
