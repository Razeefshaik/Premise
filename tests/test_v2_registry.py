"""The Kind 1 / Kind 2 firewall. Reasoning relations are a code constant; knowledge relations are data."""
from __future__ import annotations

import copy
import re
import shutil

import pytest
import yaml

from premise_v2.registry import REASONING_RELATIONS, Ext, check_relations, knowledge_relations

from conftest import ROOT, SANDBOX

QUERIES = ROOT / "premise" / "graph" / "queries"


@pytest.fixture
def registry():
    return copy.deepcopy(Ext.load(SANDBOX).relations)


def test_shipped_registry_is_valid(registry):
    assert check_relations(registry) == []
    assert {e["name"] for e in knowledge_relations(registry)} == {"ON_CALL_FOR", "VENDOR_FOR"}


def test_reasoning_set_matches_what_v1_actually_writes():
    from premise.ingest.parse import AUTHORED_EDGE_TYPES
    assert REASONING_RELATIONS <= set(AUTHORED_EDGE_TYPES)


def _entry(registry, name):
    return next(e for e in registry["relations"] if e["name"] == name)


@pytest.mark.parametrize("tamper,needle", [
    (lambda r: r["relations"].remove(_entry(r, "PROVIDES")), "must equal the code constant"),
    (lambda r: r["relations"].append({"name": "MITIGATES", "kind": "reasoning", "status": "approved", "locked": True,
                                      "domain": ["Decision"], "range": ["Assumption"]}), "must equal the code constant"),
    (lambda r: _entry(r, "REQUIRES").update(locked=False), "approved and locked"),
    (lambda r: _entry(r, "ON_CALL_FOR").update(aliases=["requires"]), "collides with a reasoning relation"),
    (lambda r: r["relations"].append({"name": "RELATED_TO", "kind": "knowledge", "status": "proposed",
                                      "domain": ["Person"], "range": ["Service"]}), "vague names"),
    (lambda r: _entry(r, "VENDOR_FOR").update(domain=[]), "domain must list known node labels"),
    (lambda r: _entry(r, "VENDOR_FOR")["examples"].update(negative=[]), "2 positive and 1 negative"),
    (lambda r: _entry(r, "VENDOR_FOR").update(status="retired"), "retirement_reason"),
    (lambda r: r["relations"].append({"name": "PAYMENT_VENDOR_FOR", "kind": "knowledge", "status": "retired",
                                      "retirement_reason": "duplicate", "same_as": "MISSING"}), "same_as must point"),
])
def test_registry_rules(registry, tamper, needle):
    tamper(registry)
    assert any(needle in e for e in check_relations(registry))


def test_verdict_queries_never_name_a_knowledge_relation(registry):
    names = {e["name"] for e in registry["relations"] if e["kind"] == "knowledge"}
    used = set()
    for q in QUERIES.glob("*.cypher"):
        used |= set(re.findall(r"\[[a-z]*:([A-Z_|]+)", q.read_text()))
    used = {part for u in used for part in u.split("|")}
    assert used and not (used & names)


def test_pipeline_refuses_a_registry_that_breaks_the_lock(tmp_path, falkordb_port):
    import redis
    from premise.graph.client import GraphClient
    from premise_v2.pipeline import Pipeline, fixture_workers
    model = tmp_path / "model"
    shutil.copytree(SANDBOX, model)
    reg = yaml.safe_load((model / "ext/relations.yaml").read_text())
    reg["relations"] = [e for e in reg["relations"] if e["name"] != "RELIES_ON"]
    (model / "ext/relations.yaml").write_text(yaml.safe_dump(reg))
    p = Pipeline(redis.Redis(port=falkordb_port), GraphClient(port=falkordb_port, graph_name="unused_s"),
                 GraphClient(port=falkordb_port, graph_name="unused_d"), model, fixture_workers(ROOT / "fixtures/v2"))
    s = p.run()
    assert s.registry_errors and s.produced == {} and s.drifts == []
