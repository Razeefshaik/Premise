from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
import yaml

from premise_v2.extract.base import ExtractionRunner
from premise_v2.extract.knowledge import KnowledgeExtractor, KnowledgeModelExtractor, RelationCandidate
from premise_v2.knowledge import KnowledgeWriter, load_knowledge, require_merged_model, validate_rows
from premise_v2.registry import Ext
from test_v2_pipeline import FakeGitHub, env, pipeline, r, stream_name
from test_v2_identity import ready
from v2_fakes import FakeAdapter


def knowledge_doc():
    return {"relations": [{"type": "ON_CALL_FOR", "from": "p_jun", "to": "paymentservice",
                           "valid_from": "2026-10-10", "valid_to": None, "evidence": ["slack:test:1"], "registry_version": 1}]}


def write_model(root, doc):
    (root / "knowledge").mkdir(exist_ok=True)
    (root / "knowledge/relations.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_deterministic_relation_proposal_and_unmatched_mentions(r, new_graph, stream_name):
    p = ready(r, new_graph, stream_name)
    p.handle(env("Jun Park is on call for paymentservice.", user="U01JUN"))
    p.handle(env("Ravi reviewed webhookingress.", key="slack:C2:2.0", user="U01RAVI"))
    s = p.run(load_decision=False)
    assert len(s.knowledge_proposals) == 1 and s.knowledge_proposals[0]["kind"] == "knowledge"
    row = p.staging.proposal(s.knowledge_proposals[0]["key"])
    doc = yaml.safe_load(row["new_text"])
    assert doc["relations"][0]["type"] == "ON_CALL_FOR" and doc["relations"][0]["from"] == "p_jun"
    unmatched = p.staging.c.read("MATCH (u:UnmatchedMention) WHERE u.active RETURN u.phrase AS p")
    assert unmatched == [{"p": "reviewed"}]
    assert not (p.model_root / "knowledge/relations.yaml").exists()


def test_llm_fallback_has_approved_enum_and_literal_grounding(r, new_graph, stream_name):
    p = ready(r, new_graph, stream_name)
    text = "Paylane supplies webhookingress."
    p.handle(env(text))
    c = {"quote": text, "relation": "VENDOR_FOR", "from_id": "paylane", "from_mention": "Paylane",
         "to_id": "webhookingress", "to_mention": "webhookingress", "relation_words": ["supplies"]}
    extractor = KnowledgeModelExtractor(p.decision, p.model_root)
    assert len(extractor.catalog.mentions(text)) == 2, extractor.catalog.mentions(text)
    assert extractor.unmatched(p.staging.items()[0]), extractor.catalog.mentions(text)
    adapter = FakeAdapter([{"candidates": [c]}])
    stats = ExtractionRunner(p.staging, [extractor], adapter, "codex-cli").run(p.staging.items())
    assert stats["model_calls"] == 1, stats["skipped"]
    assert stats["grounded"] == 1, stats
    assert "REQUIRES" not in extractor.schema.model_json_schema()["properties"]["relation"]["enum"]
    assert extractor.ground(RelationCandidate(**{**c, "from_id": "p_jun"}), text) == (False, "unknown_entity")
    assert extractor.ground(RelationCandidate(**{**c, "relation_words": ["invented"]}), text) == (False, "relation_not_in_quote")


def test_new_rotation_ends_old_row_and_preserves_history(r, new_graph, stream_name, repo_copy):
    doc = knowledge_doc()
    write_model(repo_copy, doc)
    p = ready(r, new_graph, stream_name, repo_copy)
    before = (repo_copy / "knowledge/relations.yaml").read_bytes()
    p.handle(env("Ravi Menon is on call for paymentservice.", user="U01RAVI"))
    s = p.run(load_decision=False)
    result = yaml.safe_load(p.staging.proposal(s.knowledge_proposals[0]["key"])["new_text"])
    assert len(result["relations"]) == 2
    assert result["relations"][0]["from"] == "p_jun" and result["relations"][0]["valid_to"]
    assert result["relations"][1]["from"] == "p_ravi" and result["relations"][1]["valid_to"] is None
    assert (repo_copy / "knowledge/relations.yaml").read_bytes() == before


def test_loader_is_separate_idempotent_and_contains_no_kind_one(r, new_graph, stream_name, repo_copy, monkeypatch):
    write_model(repo_copy, knowledge_doc())
    p = ready(r, new_graph, stream_name, repo_copy)
    knowledge = new_graph()
    baseline = p.decision.read("MATCH (n) RETURN count(n) AS n")
    monkeypatch.setattr(p.decision, "write", lambda *a, **k: pytest.fail("loader wrote the decision graph"))
    a = load_knowledge(knowledge, p.decision, repo_copy)
    b = load_knowledge(knowledge, p.decision, repo_copy)
    assert a == b and a["rows"] == 1
    assert knowledge.read("MATCH ()-[r]->() RETURN type(r) AS type") == [{"type": "ON_CALL_FOR"}]
    assert p.decision.read("MATCH (n) RETURN count(n) AS n") == baseline
    with pytest.raises(ValueError, match="separate"):
        load_knowledge(p.decision, p.decision, repo_copy)
    query_root = Path(__file__).resolve().parents[1] / "premise/graph/queries"
    assert all("premise_knowledge" not in file.read_text() for file in query_root.glob("*.cypher"))


def test_private_knowledge_quote_is_withheld(r, new_graph, stream_name):
    p = ready(r, new_graph, stream_name)
    text = "Jun Park is on call for paymentservice."
    e = env(text, user="U01JUN")
    e.visibility = "private"
    p.handle(e)
    s = p.run(load_decision=False)
    row = p.staging.proposal(s.knowledge_proposals[0]["key"])
    assert text not in row["body"] + row["new_text"]
    assert "private source; quote withheld" in row["body"]
    types = {r["t"] for r in p.staging.c.read("MATCH ()-[r]->() RETURN DISTINCT type(r) AS t")}
    assert not types & {"REQUIRES", "PROVIDES", "RELIES_ON"}


@pytest.mark.parametrize("collision", ["staging", "decision", "protected"])
def test_knowledge_graph_isolation_precedes_connections(r, new_graph, monkeypatch, capsys, collision):
    from types import SimpleNamespace
    from premise.config import Settings
    from premise_v2 import cli
    protected = new_graph()
    protected.write("CREATE (:Sentinel {id:'preserve'})")
    monkeypatch.setattr(cli, "settings", lambda: Settings(graph_name=protected.graph_name))
    def forbidden(**kwargs):
        pytest.fail("unsafe graph reached a connection")
    monkeypatch.setattr(cli, "redis", SimpleNamespace(Redis=forbidden))
    name = {"staging": "stage", "decision": "decision", "protected": protected.graph_name}[collision]
    assert cli.main(["--staging-graph", "stage", "--decision-graph", "decision", "--knowledge-graph", name, "load-knowledge"]) == 2
    assert "knowledge" in capsys.readouterr().err
    assert protected.read("MATCH (n:Sentinel) RETURN n.id AS id") == [{"id": "preserve"}]


@pytest.mark.parametrize("status", ["retired", "proposed"])
def test_loader_rejects_unapproved_type_before_writing(r, new_graph, stream_name, repo_copy, status):
    write_model(repo_copy, knowledge_doc())
    reg = Ext.load(repo_copy).relations
    rel = next(x for x in reg["relations"] if x["name"] == "ON_CALL_FOR")
    rel.update(status=status)
    if status == "retired":
        rel["retirement_reason"] = "outdated"
    (repo_copy / "ext/relations.yaml").write_text(yaml.safe_dump(reg), encoding="utf-8")
    p = ready(r, new_graph, stream_name, repo_copy)
    knowledge = new_graph()
    knowledge.write("CREATE (:Sentinel {id:'preserve'})")
    with pytest.raises(ValueError, match="unapproved"):
        load_knowledge(knowledge, p.decision, repo_copy)
    assert knowledge.read("MATCH (n:Sentinel) RETURN n.id AS id") == [{"id": "preserve"}]


def test_temporal_domain_and_reasoning_firewalls(r, new_graph, stream_name):
    p = ready(r, new_graph, stream_name)
    ext = Ext.load(p.model_root)
    extractor = KnowledgeExtractor(p.decision, p.model_root)
    for change, reason in [({"type": "REQUIRES"}, "unapproved"), ({"from": "paylane"}, "domain"),
                          ({"valid_to": "2026-10-01"}, "temporal")]:
        doc = knowledge_doc()
        doc["relations"][0].update(change)
        with pytest.raises(ValueError, match=reason):
            validate_rows(doc, ext.relations, extractor.catalog)


def test_loader_requires_clean_main_history(tmp_path):
    write_model(tmp_path, knowledge_doc())
    with pytest.raises(ValueError, match="committed"):
        require_merged_model(tmp_path)
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "knowledge/relations.yaml"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "-m", "reviewed knowledge"], capture_output=True, check=True)
    assert len(require_merged_model(tmp_path)) == 40
    (tmp_path / "knowledge/relations.yaml").write_text("relations: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean"):
        require_merged_model(tmp_path)
