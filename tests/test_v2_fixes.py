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
from test_v2_pipeline import FIXTURES, FakeGitHub, env, pipeline, r, stream_name


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
