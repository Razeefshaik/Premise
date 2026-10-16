from copy import deepcopy
from pathlib import Path
import yaml
import pytest

from conftest import ROOT, NOW
from premise.ingest.parse import parse_repo
from premise.ingest.run import ingest
from premise.ingest.validate import validate
from premise.reasoning.assess import assess
from premise.reasoning.models import ChangedFact
from premise_v2.decisions import DecisionWriter
from premise_v2.extract.base import ExtractionRunner
from premise_v2.extract.decision import DecisionCandidate, DecisionExtractor
from test_v2_identity import ready
from test_v2_pipeline import FakeGitHub, env, r, stream_name
from v2_fakes import FakeAdapter


def sample():
    example = yaml.safe_load((ROOT / "fixtures/v2/gold/075-tune-decision_prose.yaml").read_text())
    return example["source"]["text"], {"quote": example["source"]["text"], **example["expected"]["E1"][0]}


def prepare(r, new_graph, stream_name, model=None, private=False):
    p = ready(r, new_graph, stream_name, model)
    text, candidate = sample()
    e = env(text)
    e.visibility = "private" if private else "public"
    p.handle(e)
    runner = ExtractionRunner(p.staging, [DecisionExtractor(p.decision, p.model_root)],
                              FakeAdapter([{"candidates": [candidate]}]), "codex-cli")
    assert runner.run(p.staging.items())["grounded"] == 1
    return p


def test_valid_page_becomes_validated_inert_draft_and_review_pr(r, new_graph, stream_name, repo_copy, monkeypatch):
    p = prepare(r, new_graph, stream_name, repo_copy)
    before = p.decision.read("MATCH (n) RETURN count(n) AS n")
    monkeypatch.setattr(p.decision, "write", lambda *a, **k: pytest.fail("E1 wrote decision graph"))
    p.writer.github = FakeGitHub()
    output = DecisionWriter(p.staging, p.decision, p.model_root, p.writer).run()
    row = p.staging.proposal(output[0]["key"])
    assert output[0]["state"] == "created" and row["verdict_preview"] == "NEEDS_REVIEW"
    assert len(p.writer.github.prs) == 1
    assert "draft:" in row["new_text"] and "provides: []" in row["new_text"]
    assert not (repo_copy / row["file"]).exists()
    assert p.decision.read("MATCH (n) RETURN count(n) AS n") == before
    types = {x["type"] for x in p.staging.c.read("MATCH ()-[r]->() RETURN type(r) AS type")}
    assert not types & {"REQUIRES", "PROVIDES", "RELIES_ON"}
    again = DecisionWriter(p.staging, p.decision, p.model_root, p.writer).run()
    assert again[0]["state"] == "unchanged" and len(p.writer.github.prs) == 1


@pytest.mark.parametrize("field,value,reason", [
    ("context_quote", "A fabricated context.", "quote_not_in_source"),
    ("title", "A fabricated title", "title_not_in_quote"),
    ("governs", ["unknown_service"], "unknown_or_unquoted_service"),
    ("requires", [{"guarantee_index": 2, "assumption_index": 0}], "invalid_requirement_index"),
])
def test_draft_grounding_rejects_ungrounded_fields(r, new_graph, stream_name, field, value, reason):
    p = ready(r, new_graph, stream_name)
    text, candidate = sample()
    candidate[field] = value
    assert DecisionExtractor(p.decision, p.model_root).ground(DecisionCandidate.model_validate(candidate), text) == (False, reason)


@pytest.mark.parametrize("change,reason", [
    ({"lhs_fact": "invented.fact"}, "unregistered_fact"),
    ({"lhs_fact": "paymentservice.charge_timeout_ms"}, "fact_not_in_quote"),
    ({"value": 999}, "value_not_in_quote"),
    ({"value": None}, "predicate_requires_one_rhs"),
    ({"op": ">"}, "operator_not_in_quote"),
])
def test_draft_predicates_must_be_registered_quoted_and_literal(r, new_graph, stream_name, change, reason):
    p = ready(r, new_graph, stream_name)
    text, candidate = sample()
    candidate["assumptions"][0]["check"].update(change)
    assert DecisionExtractor(p.decision, p.model_root).ground(DecisionCandidate.model_validate(candidate), text) == (False, reason)


def test_private_draft_never_creates_public_file_pr_or_dry_artifact(r, new_graph, stream_name, tmp_path):
    p = prepare(r, new_graph, stream_name, private=True)
    p.writer.github, p.writer.out = FakeGitHub(), tmp_path
    output = DecisionWriter(p.staging, p.decision, p.model_root, p.writer).run()
    assert output[0]["state"] == "private_review_only"
    assert not p.staging.proposals() and not p.writer.github.prs and not list(tmp_path.iterdir())
    assert p.staging.review_items("decision")[0]["data"]["evidence"][0]["visibility"] == "private"


def test_v1_validator_rejects_requires_cycle_before_any_proposal(r, new_graph, stream_name, monkeypatch):
    import premise_v2.decisions as module
    p = prepare(r, new_graph, stream_name)
    render = module.render_draft
    def cycle(candidate, suffix, active=False):
        text = render(candidate, suffix, active)
        if active:
            text = text.replace(f"- A_DRAFT_{suffix}_0", f"- G_DRAFT_{suffix}_0")
        return text
    monkeypatch.setattr(module, "render_draft", cycle)
    result = DecisionWriter(p.staging, p.decision, p.model_root, p.writer).run()
    assert result[0]["state"] == "skipped" and "REQUIRES cycle" in result[0]["reason"]
    assert not p.staging.proposals()


def test_ingesting_proposed_draft_cannot_add_guarantees_assumptions_or_change_verdict(r, new_graph, stream_name, repo_copy):
    p = prepare(r, new_graph, stream_name, repo_copy)
    model_before = parse_repo(repo_copy)
    changes = [ChangedFact(fact="paylane.retry_window_hours", file="config/partners/paylane.yaml", old=24, new=72)]
    before = assess(p.decision, changes, at_ms=NOW)
    output = DecisionWriter(p.staging, p.decision, p.model_root, p.writer).run()
    row = p.staging.proposal(output[0]["key"])
    (repo_copy / row["file"]).write_text(row["new_text"], encoding="utf-8")
    model_after = parse_repo(repo_copy)
    assert not validate(model_after)[0]
    for label in ("Guarantee", "Assumption", "Fact"):
        assert model_before.nodes[label] == model_after.nodes[label]
    assert model_before.guarantee_requires == model_after.guarantee_requires
    graph = new_graph()
    ingest(graph, repo_copy, "proposed-draft")
    after = assess(graph, changes, at_ms=NOW)
    assert before.verdict == after.verdict == "BLOCKED"
    assert [(g.id, g.status) for g in before.guarantees] == [(g.id, g.status) for g in after.guarantees]


def test_pipeline_uses_shared_budget_and_cache_for_e1(r, new_graph, stream_name):
    p = ready(r, new_graph, stream_name)
    text, candidate = sample()
    p.handle(env(text))
    p.adapter, p.llm_provider, p.model_budget = FakeAdapter([{"candidates": [candidate]}]), "codex-cli", 1
    result = p.run(load_decision=False)
    assert result.extraction["model_calls"] == 1 and result.decision_proposals[0]["state"] == "created"
    p.adapter.calls.clear()
    result = p.run(load_decision=False)
    assert not p.adapter.calls and result.extraction["cache_hits"] >= 1
    assert result.decision_proposals[0]["state"] == "unchanged"
