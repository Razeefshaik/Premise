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
from test_v2_pipeline import FakeGitHub, env, pipeline, r, stream_name


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
