"""Command line entry point: premise ingest | assess-scenario | scenarios."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .graph.client import GraphClient
from .ingest.run import IngestionError, ingest
from .scenarios import check, load_scenarios, run_scenario, scenario_now


def main(argv: list[str] | None = None) -> int:
    s = settings()
    ap = argparse.ArgumentParser(prog="premise")
    ap.add_argument("--graph", default=s.graph_name)
    ap.add_argument("--port", type=int, default=s.falkordb_port)
    ap.add_argument("--host", default=s.falkordb_host)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--repo", default=s.sandbox_dir)
    p_ing.add_argument("--sha", default="local")
    p_ing.add_argument("--url", default=None)
    p_one = sub.add_parser("assess-scenario")
    p_one.add_argument("name")
    p_one.add_argument("--repo", default=s.sandbox_dir)
    p_one.add_argument("--file", default="scenarios/scenarios.yaml")
    p_all = sub.add_parser("scenarios")
    p_all.add_argument("--repo", default=s.sandbox_dir)
    p_all.add_argument("--file", default="scenarios/scenarios.yaml")
    args = ap.parse_args(argv)

    client = GraphClient(args.host, args.port, args.graph)
    if args.cmd == "ingest":
        try:
            r = ingest(client, args.repo, args.sha, args.url)
        except IngestionError as exc:
            print("ingestion failed:\n  " + "\n  ".join(exc.errors), file=sys.stderr)
            return 1
        print(f"revision {r.rev}: {r.node_count} nodes, {r.edge_count} authored edges")
        for w in r.warnings:
            print(f"warning: {w}")
        return 0

    data = load_scenarios(args.file)
    now = scenario_now(data)
    if args.cmd == "assess-scenario":
        res = run_scenario(client, Path(args.repo), data["scenarios"][args.name], now, data.get("since_days", 180))
        print(json.dumps(res.model_dump(), indent=2, default=str))
        return 0

    failures = 0
    print(f"{'scenario':<10} {'verdict':<20} {'result':<6} detail")
    for name, sc in data["scenarios"].items():
        res = run_scenario(client, Path(args.repo), sc, now, data.get("since_days", 180))
        problems = check(res, sc["expect"])
        failures += bool(problems)
        print(f"{name:<10} {res.verdict:<20} {'PASS' if not problems else 'FAIL':<6} {'; '.join(problems)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
