from pathlib import Path
import shutil
import json
import inspect

import pytest

from premise_v2.envelope import Envelope
from premise_v2.extract import FactClaimExtractor, ground
from premise_v2.gold import corpus, run_gold, semantic, score, annotated_equal
from premise_v2.registry import Ext
from premise_v2.replay import FakeAdapter, digest
from conftest import ROOT, SANDBOX, SERVER_HOST


def test_gold_frozen_counts_categories_and_tamper_detection(tmp_path):
    manifest, examples = corpus(ROOT / "fixtures/v2/gold")
    assert len(examples) == 80 and manifest["human_review"] == "pending_razeef"
    assert len([e for e in examples if e["split"] == "holdout"]) == 40
    assert len({e["id"] for e in examples}) == 80
    assert {e["category"] for e in examples} == {
        "negatives", "hedges_or_jokes", "supersession", "unit_conversions", "injected_instructions",
        "identity_cases", "attestation_evidence", "kind2_relations", "decision_prose"}
    shutil.copytree(ROOT / "fixtures/v2/gold", tmp_path / "gold", ignore=shutil.ignore_patterns("recordings"))
    name = next(iter(manifest["files"]))
    with (tmp_path / "gold" / name).open("a") as f:
        f.write("\n# changed")
    with pytest.raises(ValueError, match="changed after freezing"):
        corpus(tmp_path / "gold")


@pytest.mark.parametrize("text,value,previous", [
    ("Paylane retries for 1.5 days.", 36, None),
    ("Paylane changed webhook retries from 24 hours to 3 days.", 72, 24),
    ("Paylane changed webhook retries from 24 to 72 hours.", 72, 24),
])
def test_decimal_and_mixed_unit_old_values(text, value, previous):
    ext = Ext.load(SANDBOX)
    env = Envelope(source="slack", kind="message", native_id="test", entity_key="slack:test",
                   sequence=1, time="2026-10-17T00:00:00Z", text=text)
    claims, _ = FactClaimExtractor(ext).extract(env, "slack:test")
    assert len(claims) == 1 and claims[0].value == value and claims[0].previous == previous
    assert ground(claims[0], text, ext) == (True, "ok")


def test_replay_rejects_changed_source_or_prompt():
    adapter = FakeAdapter([{}], [{"system_hash": digest("system"), "payload_hash": digest("source")}])
    with pytest.raises(AssertionError, match="no longer matches"):
        adapter.structured("system", "different source")


def test_rules_and_prompts_match_the_pre_holdout_freeze():
    freeze = json.loads((ROOT / "fixtures/v2/gold/recordings/freeze.json").read_text())
    assert all(digest((ROOT / f).read_text(encoding="utf-8")) == h for f, h in freeze["files"].items())


def test_e1_rules_and_scoring_match_the_pre_holdout_freeze():
    freeze = json.loads((ROOT / "fixtures/v2/gold/recordings/freeze-e1.json").read_text())
    assert all(digest((ROOT / f).read_text(encoding="utf-8")) == h for f, h in freeze["files"].items())
    for function in (semantic, score, annotated_equal):
        assert digest(inspect.getsource(function)) == freeze["scoring"][function.__name__]


def test_real_recordings_replay_above_holdout_floors_without_live_calls(falkordb_port, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("gold CI must never construct a live model or API")
    monkeypatch.setattr("premise.agent.llm.make_adapter", forbidden)
    monkeypatch.setattr("premise.github.api.GitHub.__init__", forbidden)
    report = run_gold(SERVER_HOST, falkordb_port, SANDBOX, ROOT / "fixtures/v2/gold")
    assert not report["floor_failures"], report["floor_failures"]
    for data in report["splits"].values():
        assert data["injected_grounded_candidates"] == 0
        assert data["identity"] == {"correct": 4, "total": 4}
        for name, row in data["extractors"].items():
            assert row["exact_quote_rate"] == 1 or row["predicted"] == 0
