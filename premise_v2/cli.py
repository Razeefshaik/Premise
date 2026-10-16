"""premise-v2 run | eval | registry-check | reset"""
from __future__ import annotations

import argparse
import json
import os
import sys

import redis

from premise.config import settings
from premise.graph.client import GraphClient, GraphUnavailable

from .pipeline import Pipeline, fixture_workers
from .registry import Ext, check_relations


def check_isolation(staging: str, decision: str, protected: set[str]) -> list[str]:
    errors = []
    if staging == decision:
        errors.append("staging and decision graphs must differ")
    for name, role in ((staging, "staging"), (decision, "decision")):
        if name in protected:
            errors.append(f"{role} graph '{name}' is protected (used by v1)")
    return errors


def main(argv: list[str] | None = None) -> int:
    s = settings()
    ap = argparse.ArgumentParser(prog="premise-v2")
    ap.add_argument("--host", default=s.falkordb_host)
    ap.add_argument("--port", type=int, default=s.falkordb_port)
    ap.add_argument("--staging-graph", default=os.getenv("V2_STAGING_GRAPH", "premise_v2_staging"))
    ap.add_argument("--decision-graph", default=os.getenv("V2_DECISION_GRAPH", "premise_v2_decision"))
    ap.add_argument("--knowledge-graph", default=os.getenv("V2_KNOWLEDGE_GRAPH", "premise_knowledge"))
    ap.add_argument("--model", default=s.sandbox_dir, help="model repo root (KIF layout)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="collect fixtures, reconcile, write proposals (dry run by default)")
    run.add_argument("--fixtures", default="fixtures/v2")
    run.add_argument("--out", default=".runtime/v2/proposals")
    run.add_argument("--open-prs", action="store_true", help="open PRs on SANDBOX_REPO (needs V2_OPEN_PRS=true)")
    run.add_argument("--model-prefix", default="", help="path of the model repo inside the GitHub repo")
    run.add_argument("--github-source", action="append", default=[], metavar="OWNER/REPO", help="read-only GitHub evidence source")
    run.add_argument("--pages", action="append", default=[], metavar="FOLDER", help="read markdown exports")
    run.add_argument("--llm-provider", choices=["none", "codex-cli"], default=s.llm_provider if s.llm_provider == "codex-cli" else "none")
    run.add_argument("--model-budget", type=int, default=40)
    run.add_argument("--open-challenges", action="store_true", help="publish attestation issues (requires V2_OPEN_ISSUES=true)")
    sub.add_parser("registry-check")
    knowledge = sub.add_parser("load-knowledge", help="load reviewed knowledge from a clean merged model repo")
    knowledge.add_argument("--model", default=argparse.SUPPRESS)
    ev = sub.add_parser("eval")
    ev.add_argument("--fixtures", default="fixtures/v2")
    ev.add_argument("--write", default="docs/V2_EVAL.md")
    ev.add_argument("--gold", action="store_true", help="replay the frozen synthetic gold set; never call a live model")
    serve = sub.add_parser("serve", help="local evidence review page; no model or GitHub calls")
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", dest="web_port", type=int, default=8002)
    sub.add_parser("reset", help="delete the v2 staging graph and stream (never the decision graph of v1)")
    args = ap.parse_args(argv)

    if args.cmd == "registry-check":
        errors = check_relations(Ext.load(args.model).relations)
        print("registry ok" if not errors else "\n".join(errors))
        return 1 if errors else 0
    protected = {s.graph_name, "premise_codex_demo"}
    protected.update(name.strip() for name in os.getenv("V2_PROTECTED_GRAPHS", "").split(",") if name.strip())
    errors = check_isolation(args.staging_graph, args.decision_graph, protected)
    if args.knowledge_graph in protected:
        errors.append(f"knowledge graph '{args.knowledge_graph}' is protected (used by v1)")
    if args.knowledge_graph in {args.staging_graph, args.decision_graph}:
        errors.append("knowledge, staging and decision graphs must differ")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    args.protected_graphs = protected
    try:
        return _execute(args, s)
    except (GraphUnavailable, redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
        print(f"Cannot reach FalkorDB at {args.host}:{args.port}. Start it with: docker compose up -d falkordb "
              '(check FALKORDB_HOST in .env: use 127.0.0.1 when running on Windows, not "falkordb")', file=sys.stderr)
        return 3


def _execute(args: argparse.Namespace, s) -> int:
    r = redis.Redis(host=args.host, port=args.port)
    staging = GraphClient(args.host, args.port, args.staging_graph)
    decision = GraphClient(args.host, args.port, args.decision_graph)
    if args.cmd == "serve":
        import uvicorn
        from .staging import Staging
        from .web import create_app
        app = create_app(Staging(staging), decision, GraphClient(args.host, args.port, args.knowledge_graph),
                         args.model, bind=args.bind)
        uvicorn.run(app, host=args.bind, port=args.web_port, proxy_headers=False)
        return 0
    if args.cmd == "load-knowledge":
        from premise.ingest.run import ingest
        from .knowledge import load_knowledge, require_merged_model
        try:
            sha = require_merged_model(args.model)
            ingest(decision, args.model, sha)
            result = load_knowledge(GraphClient(args.host, args.port, args.knowledge_graph), decision, args.model, args.protected_graphs)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "reset":
        staging.delete_graph()
        r.delete("premise:v2:raw", "premise:v2:raw:dead", "premise:v2:raw:failures")
        print("v2 staging graph and stream deleted")
        return 0
    if args.cmd == "eval":
        if args.gold:
            from .gold import run_gold, write_markdown
            report = run_gold(args.host, args.port, args.model, str(__import__("pathlib").Path(args.fixtures) / "gold"))
            if args.write:
                write_markdown(report, args.write)
            print(json.dumps(report, indent=2, default=str))
            return 1 if report["floor_failures"] else 0
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
    issue_github = None
    if args.open_challenges:
        if os.getenv("V2_OPEN_ISSUES", "false").lower() != "true" or not s.github_token:
            print("live issues need V2_OPEN_ISSUES=true and GITHUB_TOKEN", file=sys.stderr)
            return 1
        from premise.github.api import GitHub
        issue_github = GitHub(s.sandbox_repo, s.github_token)
    adapter = None
    if args.llm_provider == "codex-cli":
        from dataclasses import replace
        from premise.agent.llm import make_adapter
        adapter = make_adapter(replace(s, llm_provider="codex-cli"))
    from .connectors import GitHubConnector, PagesConnector
    from premise.github.api import GitHub
    sources = [GitHub(repo, s.github_token) for repo in args.github_source]
    workers = fixture_workers(args.fixtures) + [GitHubConnector(repo, github=client) for repo, client in zip(args.github_source, sources)]
    workers += [PagesConnector(path) for path in args.pages]
    try:
        summary = Pipeline(r, staging, decision, args.model, workers, args.out, github,
                           model_prefix=args.model_prefix, adapter=adapter, llm_provider=args.llm_provider,
                           model_budget=args.model_budget, issue_github=issue_github).run()
    finally:
        for client in sources:
            client.close()
        if github is not None:
            github.close()
        if issue_github is not None:
            issue_github.close()
    print(json.dumps(summary.__dict__, indent=2, default=str))
    return 1 if summary.registry_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
