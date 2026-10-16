"""Frozen synthetic evaluation; replay never constructs a live adapter."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import uuid

import yaml

from premise.graph.client import GraphClient
from premise.ingest.run import ingest
from .envelope import Envelope
from .extract import FactClaimExtractor, INSTRUCTION, body_of, ground
from .extract.attestation import AttestationExtractor
from .extract.base import ExtractionRunner
from .extract.knowledge import KnowledgeExtractor, KnowledgeModelExtractor
from .identity import IdentityDirectory, account_of
from .registry import Ext
from .replay import FakeAdapter, digest
from .staging import Staging

FLOORS = {"E2": .95, "E3": .85, "K2": .85}


def corpus(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if len(manifest["files"]) != 80 or manifest["splits"] != {"tune": 40, "holdout": 40}:
        raise ValueError("gold corpus must contain a frozen 40/40 split")
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.yaml")}
    if actual != manifest["files"] or digest(json.dumps(actual, sort_keys=True)) != manifest["corpus_hash"]:
        raise ValueError("gold corpus changed after freezing")
    examples = [yaml.safe_load((root / name).read_text(encoding="utf-8")) for name in sorted(actual)]
    return manifest, examples


class RecordingAdapter:
    """Record real structured responses before any schema or grounding decisions."""
    def __init__(self, adapter):
        self.adapter, self.requests = adapter, []
        self.model = getattr(adapter, "model", "") or "configured-default"

    def structured(self, system, payload):
        started = time.monotonic()
        response = self.adapter.structured(system, payload)
        self.requests.append({"system_hash": digest(system), "payload_hash": digest(payload),
                              "system": system, "payload": payload, "response": response,
                              "seconds": time.monotonic() - started})
        return response


def semantic(name, row):
    fields = {"E2": ("fact", "value", "status"), "E3": ("assumption_id", "stance"),
              "K2": ("relation", "from_id", "to_id", "action"), "E1": ("title",)}[name]
    return tuple(json.dumps(row.get(f, "add" if f == "action" else None), sort_keys=True) for f in fields)


def score(name, expected, actual):
    expected = {semantic(name, r): r for r in expected}
    actual = {semantic(name, r): r for r in actual}
    matched = expected.keys() & actual.keys()
    # Field accuracy checks annotated fields, including old units and exact quotes.
    fields, correct = 0, 0
    for key in matched:
        for field, value in expected[key].items():
            fields += 1
            correct += actual[key].get(field) == value
    return {"expected": len(expected), "predicted": len(actual), "correct": len(matched),
            "fields": fields, "fields_correct": correct}


def run_gold(host, port, model_root, root="fixtures/v2/gold", split=None, capture=None,
             extractor_names=("E3", "K2", "K2_LLM"), budget=40):
    """capture is a real adapter only in the explicitly executed recording script."""
    root, model_root = Path(root), Path(model_root)
    manifest, examples = corpus(root)
    stage_c = GraphClient(host, port, "premise_gold_stage_" + uuid.uuid4().hex[:10])
    decision = GraphClient(host, port, "premise_gold_decision_" + uuid.uuid4().hex[:10])
    try:
        ingest(decision, model_root, "gold-frozen-model", "https://example.invalid/synthetic")
        staging = Staging(stage_c)
        ext = Ext.load(model_root)
        registry = {"E3": AttestationExtractor(decision), "K2": KnowledgeExtractor(decision, model_root),
                    "K2_LLM": KnowledgeModelExtractor(decision, model_root)}
        if "E1" in extractor_names:
            from .extract.decision import DecisionExtractor
            registry["E1"] = DecisionExtractor(decision, model_root)
        result = {"corpus_hash": manifest["corpus_hash"], "human_review": manifest["human_review"],
                  "provenance": "actual codex-cli recordings replayed through FakeAdapter",
                  "splits": {}, "floor_failures": []}
        for which in ([split] if split else ["tune", "holdout"]):
            totals, errors, calls_left = {}, [], budget
            identity_correct = identity_total = injections = 0
            for example in (e for e in examples if e["split"] == which):
                env = Envelope.model_validate(example["source"])
                item = {"key": env.entity_key, "body": body_of(env), "hash": env.content_hash,
                        "cls": "chat" if env.kind == "message" else "doc", "sequence": env.sequence,
                        "time_ms": int(env.time.timestamp() * 1000), "account": account_of(env)}
                stage_c.write("MERGE (i:Item {key:$k}) SET i.sequence=$s, i.deleted=false",
                              {"k": item["key"], "s": env.sequence})
                found = {"E2": [], "E3": [], "K2": [], "E1": []}
                stat_rows = {}
                if not INSTRUCTION.search(item["body"]):
                    candidates, _ = FactClaimExtractor(ext).extract(env, item["account"])
                    for c in candidates:
                        ok, why = ground(c, item["body"], ext)
                        if ok:
                            found["E2"].append(asdict(c))
                        else:
                            stat_rows.setdefault("E2", Counter())[why] += 1
                for name in extractor_names:
                    extractor = registry[name]
                    filename = root / "recordings" / f'{example["id"]}-{name}.json'
                    record = None
                    if extractor.needs_model:
                        if filename.exists():
                            record = json.loads(filename.read_text(encoding="utf-8"))
                            if record["corpus_hash"] != manifest["corpus_hash"] or record["version"] != extractor.version:
                                raise ValueError(f"stale recording: {filename.name}")
                            adapter = FakeAdapter([r["response"] for r in record["requests"]],
                                                  record["requests"], record["requested_model"])
                        elif capture is not None:
                            adapter = RecordingAdapter(capture)
                        else:
                            raise ValueError(f"missing real recording: {filename.name}; run scripts/record_v2_gold.py")
                    else:
                        adapter = None
                    runner = ExtractionRunner(staging, [extractor], adapter, "codex-cli", calls_left)
                    stats = runner.run([item])
                    calls_left -= stats["model_calls"]
                    if stats["failures"] or any("budget_exhausted" in k for k in stats["skipped"]):
                        raise ValueError(f'{example["id"]}/{name}: model failed, prompt mismatch, or budget exhausted')
                    if extractor.needs_model:
                        if isinstance(adapter, FakeAdapter) and (adapter.responses or adapter.requests):
                            raise ValueError(f"recording was not fully consumed: {filename.name}")
                        if record is None:
                            record = {"provider": "codex-cli", "requested_model": adapter.model, "resolved_model": None,
                                      "corpus_hash": manifest["corpus_hash"], "extractor": name, "version": extractor.version,
                                      "source_hash": env.content_hash, "requests": adapter.requests}
                            filename.parent.mkdir(parents=True, exist_ok=True)
                            filename.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                            print(f'recorded {example["id"]}/{name}: {len(adapter.requests)} call(s)', flush=True)
                        stats["seconds"] = sum(r["seconds"] for r in record["requests"])
                    metric = "K2" if name == "K2_LLM" else name
                    counter = totals.setdefault(metric, Counter())
                    counter.update({k: stats[k] for k in ("model_calls", "seconds", "schema_valid", "schema_invalid")})
                    counter.update({"rejected:" + k: v for k, v in stats["rejections"].items()})
                    rows = stage_c.read("MATCH (e:Extraction) WHERE e.item=$i AND e.extractor=$n AND e.grounded=true RETURN e.data_json AS d",
                                        {"i": item["key"], "n": name})
                    for row in rows:
                        candidate = json.loads(row["d"])
                        if name == "E3" and candidate["stance"] == "unrelated":
                            continue
                        found[metric].append(candidate)
                for name in ("E2", *[n for n in ("E3", "K2", "E1") if n in totals]):
                    counts = score(name, example["expected"][name], found[name])
                    totals.setdefault(name, Counter()).update(counts)
                    for why, count in stat_rows.get(name, {}).items():
                        totals[name]["rejected:" + why] += count
                    for c in found[name]:
                        totals[name]["quotes"] += 1
                        # E1 has several exact source quotes; all must be exact.
                        quotes = [c["quote"]] if "quote" in c else [c["context_quote"], c["decision_quote"]]
                        totals[name]["quotes_exact"] += all(q in item["body"] for q in quotes)
                    if counts["correct"] != counts["expected"] or counts["correct"] != counts["predicted"]:
                        errors.append({"id": example["id"], "extractor": name,
                                       "expected": example["expected"][name], "actual": found[name]})
                if example["category"] == "injected_instructions":
                    injections += sum(len(v) for v in found.values())
                if "expected_identity" in example:
                    directory = IdentityDirectory(staging, decision, model_root)
                    key = directory.capture(env)
                    directory.sync()
                    links = [l for l in directory.links() if l["account"] == key]
                    actual = {"status": "unresolved", "person": None, "bridge": False}
                    if links:
                        actual = {k: links[0][k] for k in actual}
                    identity_total += 1
                    identity_correct += actual == example["expected_identity"]
                    if actual != example["expected_identity"]:
                        errors.append({"id": example["id"], "extractor": "identity",
                                       "expected": example["expected_identity"], "actual": actual})
            metrics = {}
            for name, c in totals.items():
                metrics[name] = {**dict(c),
                    "precision": c["correct"] / c["predicted"] if c["predicted"] else None,
                    "recall": c["correct"] / c["expected"] if c["expected"] else None,
                    "exact_quote_rate": c["quotes_exact"] / c["quotes"] if c["quotes"] else None,
                    "field_accuracy": c["fields_correct"] / c["fields"] if c["fields"] else None,
                    "schema_validity_rate": c["schema_valid"] / (c["schema_valid"] + c["schema_invalid"])
                        if c["schema_valid"] + c["schema_invalid"] else None}
            result["splits"][which] = {"snippets": 40, "extractors": metrics, "errors": errors,
                                      "identity": {"correct": identity_correct, "total": identity_total},
                                      "injected_grounded_candidates": injections}
            if which == "holdout":
                for name, floor in FLOORS.items():
                    precision = metrics.get(name, {}).get("precision")
                    if precision is None or precision < floor:
                        result["floor_failures"].append(f"{name} precision {precision} below {floor}")
                if injections:
                    result["floor_failures"].append("injected input produced a grounded candidate")
        return result
    finally:
        stage_c.delete_graph()
        decision.delete_graph()


def write_markdown(report, path):
    rows = ["# Phase 2 synthetic evaluation", "",
            "80 synthetic snippets; frozen 40/40 split. **Razeef's hand review is pending.**",
            "These small, author-labeled samples do not establish production accuracy.",
            "Model metrics replay actual local Codex outputs; seconds are recorded inference time, not replay time.",
            "Requested CLI default does not identify the resolved backend model.", "",
            f'Corpus SHA256: `{report["corpus_hash"]}`', "",
            "| Split | Extractor | Precision | Recall | Exact quotes | Field accuracy | Schema validity | Calls | Recorded seconds |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    def fmt(v):
        return "n/a" if v is None else f"{v:.3f}"
    notes = []
    for split, data in report["splits"].items():
        for name, m in data["extractors"].items():
            rows.append("| " + " | ".join([split, name, *[fmt(m.get(k)) for k in
                ("precision", "recall", "exact_quote_rate", "field_accuracy", "schema_validity_rate")],
                str(m.get("model_calls", 0)), fmt(m.get("seconds", 0))]) + " |")
        notes.extend(["", f'{split}: injected grounded candidates = {data["injected_grounded_candidates"]}; '
                     f'identity cases {data["identity"]["correct"]}/{data["identity"]["total"]}.',
                     "Grounding rejections: " + json.dumps({name: {k[9:]: v for k, v in m.items() if k.startswith("rejected:")}
                                                            for name, m in data["extractors"].items()})])
    rows += notes + ["", "Floor failures: " + ("; ".join(report["floor_failures"]) or "none"),
             "", "Full mismatch details: run `python -m premise_v2.cli eval --gold` (JSON output)."]
    Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")
