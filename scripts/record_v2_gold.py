"""Explicit, live local Codex capture. Never imported by tests; no GitHub writes."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from premise.config import settings
from premise.agent.llm import make_adapter
from premise_v2.gold import run_gold

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", required=True, choices=["tune", "holdout"])
    ap.add_argument("--extractors", nargs="+", default=["E3", "K2", "K2_LLM", "E1"])
    ap.add_argument("--budget", type=int, default=40)
    args = ap.parse_args()
    s = settings()
    result = run_gold(s.falkordb_host, s.falkordb_port, s.sandbox_dir, split=args.split,
                      capture=make_adapter(replace(s, llm_provider="codex-cli")), budget=args.budget,
                      extractor_names=tuple(args.extractors))
    path = Path(f".runtime/gold-{args.split}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Report: {path}", flush=True)
