"""premise-v2 run | eval | registry-check | reset"""
from __future__ import annotations

import argparse
import json
import os
import sys

import redis

from premise.config import settings
from premise.graph.client import GraphClient

from .pipeline import Pipeline, fixture_workers
from .registry import Ext, check_relations


def main(argv: list[str] | None = None) -> int:
    s = settings()
    ap = argparse.ArgumentParser(prog="premise-v2")
    ap.add_argument("--host", default=s.falkordb_host)
    ap.add_argument("--port", type=int, default=s.falkordb_port)
    ap.add_argument("--staging-graph", default=os.getenv("V2_STAGING_GRAPH", "premise_v2_staging"))
    ap.add_argument("--decision-graph", default=os.getenv("V2_DECISION_GRAPH", "premise_v2_decision"))
    ap.add_argument("--model", default=s.sandbox_dir, help="model repo root (KIF layout)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="collect fixtures, reconcile, write proposals (dry run by default)")
    run.add_argument("--fixtures", default="fixtures/v2")
    run.add_argument("--out", default=".runtime/v2/proposals")
    run.add_argument("--open-prs", action="store_true", help="open PRs on SANDBOX_REPO (needs V2_OPEN_PRS=true)")
    run.add_argument("--model-prefix", default="", help="path of the model repo inside the GitHub repo")
    sub.add_parser("registry-check")
    ev = sub.add_parser("eval")
    ev.add_argument("--fixtures", default="fixtures/v2")
    ev.add_argument("--write", default="docs/V2_EVAL.md")
    sub.add_parser("reset", help="delete the v2 staging graph and stream (never the decision graph of v1)")
    args = ap.parse_args(argv)

    if args.cmd == "registry-check":
        errors = check_relations(Ext.load(args.model).relations)
        print("registry ok" if not errors else "\n".join(errors))
        return 1 if errors else 0
    r = redis.Redis(host=args.host, port=args.port)
    staging = GraphClient(args.host, args.port, args.staging_graph)
    decision = GraphClient(args.host, args.port, args.decision_graph)
    if args.cmd == "reset":
        if args.decision_graph == s.graph_name:
            print("refusing: the decision graph name matches v1's graph", file=sys.stderr)
            return 1
        staging.delete_graph()
        r.delete("premise:v2:raw", "premise:v2:raw:dead", "premise:v2:raw:failures")
        print("v2 staging graph and stream deleted")
        return 0
    if args.cmd == "eval":
        from .evaluate import run_eval
        report = run_eval(r, args.host, args.port, args.model, args.fixtures)
        if args.write:
            from .evaluate import write_markdown
            write_markdown(report, args.write)
        print(json.dumps(report, indent=2, default=str))
        return 0
    github = None
    if args.open_prs:
        if os.getenv("V2_OPEN_PRS", "false").lower() != "true" or not s.github_token:
            print("live PRs need V2_OPEN_PRS=true and GITHUB_TOKEN", file=sys.stderr)
            return 1
        from premise.github.api import GitHub
        github = GitHub(s.sandbox_repo, s.github_token)
    summary = Pipeline(r, staging, decision, args.model, fixture_workers(args.fixtures), args.out, github,
                       model_prefix=args.model_prefix).run()
    print(json.dumps(summary.__dict__, indent=2, default=str))
    return 1 if summary.registry_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
