"""Review regressions against real FalkorDB; GitHub writes use the existing fake."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from premise.config import Settings
from premise_v2 import cli
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
