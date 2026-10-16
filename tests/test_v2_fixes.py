"""Review regressions against real FalkorDB; GitHub writes use the existing fake."""
from __future__ import annotations

from types import SimpleNamespace
import json

import pytest

from premise.config import Settings
from premise_v2 import cli
from premise_v2.propose import render_body
from premise_v2.reconcile import reconcile
from premise_v2.pipeline import fixture_workers
from premise_v2.stream import EnvelopeStream
from test_v2_pipeline import DRIFT, FIXTURES, FakeGitHub, env, pipeline, r, stream_name


@pytest.mark.parametrize("command,collision", [
    ("reset", "protected-staging"),
    ("run", "same"),
    ("run", "demo"),
    ("eval", "extra"),
])
def test_graph_isolation_before_any_connection(command, collision, new_graph, monkeypatch, capsys):
    sentinel = new_graph()
    sentinel.write("CREATE (:Sentinel {value:'preserve'})")
    config = Settings(graph_name=sentinel.graph_name)
    monkeypatch.setattr(cli, "settings", lambda: config)
    monkeypatch.setenv("V2_PROTECTED_GRAPHS", " extra-protected, other ")
    staging, decision = "isolated-staging", "isolated-decision"
    if collision == "protected-staging":
        staging = sentinel.graph_name
    elif collision == "same":
        staging = decision
    elif collision == "demo":
        decision = "premise_codex_demo"
    else:
        decision = "extra-protected"

    def forbidden(**kwargs):
        pytest.fail("isolation must be checked before constructing a connection")

    monkeypatch.setattr(cli, "redis", SimpleNamespace(Redis=forbidden))
    assert cli.main(["--staging-graph", staging, "--decision-graph", decision, command]) == 2
    assert sentinel.read("MATCH (n:Sentinel) RETURN n.value AS v") == [{"v": "preserve"}]
    message = capsys.readouterr().err
    assert ("differ" if collision == "same" else "protected") in message


def test_private_quotes_withheld_in_every_section(r, new_graph, stream_name, tmp_path):
    fixture = tmp_path / "fixtures" / "slack"
    fixture.mkdir(parents=True)
    texts = [
        "Paylane now retries for 72 hours, PrivateSupportSentinel.",
        "Paylane does not retry for 72 hours, PrivateDenialSentinel.",
        "Maybe Paylane retries for 72 hours, PrivateWeakSentinel.",
    ]
    data = {"channel": {"id": "PRIVATE", "name": "private", "is_private": True}, "users": [], "messages": [
        {"type": "message", "user": user, "ts": f"179213070{i}.000000", "text": text}
        for i, (user, text) in enumerate(zip(["U01ANIKA", "U01TESS", "U01KIM"], texts))
    ]}
    (fixture / "private.json").write_text(json.dumps(data), encoding="utf-8")
    p = pipeline(r, new_graph, stream_name, fixtures=fixture.parent)
    p.run()
    d = reconcile(p.staging, p.decision, p.model_root)[0][0]
    assert [e["visibility"] for e in d.supporting + d.disagreeing + d.weak] == ["private"] * 3
    prev = {"verdict": "BLOCKED", "not_holding": [], "verified_fixes": []}
    for missing_visibility in (False, True):
        if missing_visibility:
            for e in d.supporting + d.disagreeing + d.weak:
                e.pop("visibility")
        body = render_body(d, prev, {})
        assert not any(marker in body for marker in ("PrivateSupportSentinel", "PrivateDenialSentinel", "PrivateWeakSentinel"))
        assert body.count("(private source; quote withheld)") == 3


def test_slack_root_and_reply_are_one_origin(r, new_graph, stream_name):
    p = pipeline(r, new_graph, stream_name)
    p.workers = []
    p.staging.setup()
    p.load_decision_graph()
    root = "slack:C1:1.0"
    p.handle(env("Paylane now retries for 72 hours.", key=root, user="U01ANIKA"))
    p.handle(env("Yes, Paylane retries for 72 hours.", key="slack:C1:2.0", user="U01RAVI", thread=root))
    assert len(p.staging.active_claims()) == 2
    s = p.run(load_decision=False)
    assert s.drifts[0]["support"] == "observed"
    assert s.drifts[0]["origins"] == [[root, "slack:C1:2.0"]]
    assert s.proposals[0]["state"] == "skipped"


@pytest.mark.parametrize("newer_first", [False, True])
def test_connector_scopes_own_cursors_and_deletions(r, new_graph, stream_name, tmp_path, newer_first):
    root = tmp_path / "fixtures"
    (root / "slack").mkdir(parents=True)
    times = ["1792130820.000000", "1792130700.000000"] if newer_first else ["1792130700.000000", "1792130820.000000"]
    for n, ts in enumerate(times):
        data = {"channel": {"id": f"C{n}", "name": f"channel{n}"}, "users": [], "messages": [
            {"type": "message", "ts": ts, "user": ["U01ANIKA", "U01JUN"][n],
             "text": "Paylane now retries for 72 hours."}]}
        (root / "slack" / f"{n}.json").write_text(json.dumps(data), encoding="utf-8")
    p = pipeline(r, new_graph, stream_name, fixtures=root)
    p.run()
    live = lambda: {row["k"] for row in p.staging.c.read("MATCH (i:Item) WHERE NOT i.deleted RETURN i.key AS k")}
    expected = {f"slack:C{n}:{ts}" for n, ts in enumerate(times)}
    assert live() == expected
    p.workers = fixture_workers(root)
    assert p.run(load_decision=False).tombstones == 0
    assert live() == expected
    (root / "slack/0.json").write_text(json.dumps({"channel": {"id": "C0"}, "messages": []}), encoding="utf-8")
    p.workers = fixture_workers(root)
    assert p.run(load_decision=False).tombstones == 1
    assert live() == {f"slack:C1:{times[1]}"}
    deleted = p.staging.item(f"slack:C0:{times[0]}")
    assert deleted["scope"] == "slack:C0"
    assert p.staging.live_keys("slack:C1") == live()


def test_workers_emit_connector_scopes(r, new_graph, stream_name):
    p = pipeline(r, new_graph, stream_name)
    p.run()
    for w in fixture_workers(FIXTURES):
        envelopes = list(w.fetch(None))
        assert envelopes and all(e.scope == w.scope for e in envelopes)
        assert p.staging.live_keys(w.scope) == w.list_keys()


def test_noop_edit_advances_version_before_late_older_edit(r, new_graph, stream_name):
    p = pipeline(r, new_graph, stream_name)
    p.staging.setup()
    p.handle(env("Paylane now retries for 72 hours.", seq=1))
    p.handle(env("Paylane now retries for 72 hours.", seq=3))
    p.handle(env("Paylane now retries for 48 hours.", seq=2))
    assert p.summary.gateway == {"stored": 1, "duplicate": 1, "stale": 1}
    latest = p.staging.latest_version("slack:C1:1.0")
    assert latest["sequence"] == 3 and latest["processed"]
    claims = p.staging.active_claims()
    assert [(c["value"], c["sequence"]) for c in claims] == [(72, 1)]


@pytest.mark.parametrize("consumer", ["A", "B"])
def test_recovery_drains_all_pending_pages(r, stream_name, consumer):
    s = EnvelopeStream(r, stream=stream_name, dead=f"{stream_name}:dead", failures=f"{stream_name}:failures")
    s.ensure_group()
    for n in range(201):
        s.produce(env("entry", key=f"slack:C1:{n}.0"))
    r.xreadgroup(s.group, "A", {stream_name: ">"}, count=201)
    seen = []
    stats = s.consume(consumer, lambda e: seen.append(e.entity_key), count=100, min_idle_ms=0)
    assert len(seen) == len(set(seen)) == stats.processed == 201
    assert stats.pending_after == s.pending() == 0
    if consumer == "B":
        assert stats.reclaimed == 201


def test_poison_is_tried_once_per_run_while_good_entries_complete(r, stream_name):
    s = EnvelopeStream(r, stream=stream_name, dead=f"{stream_name}:dead", failures=f"{stream_name}:failures")
    s.produce(env("poison"))
    for n in range(50):
        s.produce(env("good", key=f"slack:GOOD:{n}.0"))
    attempts, good = [], []

    def handle(e):
        if e.text == "poison":
            attempts.append(e.entity_key)
            raise RuntimeError("poison")
        good.append(e.entity_key)

    for run in range(3):
        stats = s.consume("A", handle, count=10, min_idle_ms=0)
        assert len(attempts) == run + 1
        assert stats.failed == 1 and len(good) == 50
        assert stats.pending_after == (0 if run == 2 else 1)
    assert r.xlen(s.dead) == 1


def test_pending_stream_prevents_proposals_until_caught_up(r, new_graph, stream_name):
    gh = FakeGitHub()
    p = pipeline(r, new_graph, stream_name, github=gh)
    p.stream.ensure_group()
    p.stream.produce(env("temporarily unavailable item"))
    r.xreadgroup(p.stream.group, "other-consumer", {stream_name: ">"}, count=1)
    s = p.run()
    assert s.proposals == [] and not gh.calls and not gh.prs
    assert not s.caught_up and s.stream["pending_after"] == 1
    assert s.proposal_skip_reason == "stream not caught up"
    p.stream.consume("other-consumer", p.handle)
    s = p.run(load_decision=False)
    assert s.caught_up and s.stream["pending_after"] == 0
    assert len(gh.prs) == 1


def test_dry_then_live_publishes_once_and_tracks_remote_document(r, new_graph, stream_name):
    p = pipeline(r, new_graph, stream_name)
    p.run()
    stored = p.staging.proposal(DRIFT)
    assert not any(stored.get(k) for k in ("pr_url", "pr_number", "published_hash"))
    gh = FakeGitHub()
    p.writer.github = gh
    s = p.run(load_decision=False)
    assert len(gh.prs) == 1 and s.proposals[0]["pr_url"].endswith("/pull/1")
    stored = p.staging.proposal(DRIFT)
    assert stored["pr_number"] == 1 and stored["published_hash"] == stored["body_hash"]
    assert stored["remote_state"] == "open"
    gh.calls.clear()
    p.run(load_decision=False)
    assert not gh.calls and len(gh.prs) == 1
