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
    p_bench = sub.add_parser('bench', help='Frozen, local graph/keyword/vector benchmark')
    p_bench.add_argument('action', choices=['run'])
    p_bench.add_argument('--download-model', action='store_true')
    p_redteam = sub.add_parser('redteam', help='Run adversarial regressions and write the real report')
    p_redteam.add_argument('action', choices=['report'])
    p_check = sub.add_parser('check', help='Read-only preflight; 2 blocked, 1 review/error, 0 clear')
    p_check.add_argument('--set', action='append', default=[], dest='sets')
    p_check.add_argument('--file', action='append', default=[], dest='files')
    p_check.add_argument('--repo', default='.')
    p_check.add_argument('--json', action='store_true')
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
    p_assess = sub.add_parser("assess")
    p_assess.add_argument("--pr",type=int,required=True)
    p_assess.add_argument("--json",action="store_true")
    p_assess.add_argument("--execute",action="store_true",help="Post statuses/comments; may open a fix PR if AUTO_FIX_PR=true")
    sub.add_parser("health")
    p_ask=sub.add_parser("ask")
    p_ask.add_argument("question")
    p_serve=sub.add_parser("serve")
    p_serve.add_argument("--bind",default="127.0.0.1")
    p_serve.add_argument("--web-port",type=int,default=8000)
    sub.add_parser("mcp")
    sub.add_parser("poll-once")
    sub.add_parser("reconcile")
    p_steward=sub.add_parser('steward',help='Plan knowledge maintenance; writes require --execute')
    p_steward.add_argument('--execute',action='store_true')
    sub.add_parser("demo",help="Persist locally evaluated scenarios for browsing; no GitHub calls")
    p_reset=sub.add_parser("reset")
    p_reset.add_argument("--demo",action="store_true",required=True)
    args = ap.parse_args(argv)

    client = GraphClient.from_settings(s, host=args.host, port=args.port, graph_name=args.graph)
    if args.cmd == 'redteam':
        from .redteam import report
        result = report(args.host,args.port)
        print(json.dumps(result))
        return result['exit_code']
    if args.cmd == 'bench':
        from .benchmark.run import run, write_report
        result = run(client, download=args.download_model)
        write_report(result)
        print(json.dumps({'recorded_at':result['recorded_at'],'summary':result['summary']},indent=2))
        return 0
    if args.cmd == 'steward':
        from .github.api import GitHub
        from .github.steward import Steward
        github=GitHub(s.sandbox_repo,s.github_token)
        try:
            print(json.dumps(Steward(client,github,since_days=s.since_days).run(execute=args.execute),indent=2))
            return 0
        finally:
            github.close()
    if args.cmd == 'check':
        from .reasoning.preflight import check_proposal, repo_path
        from .graph.client import GraphUnavailable
        try:
            if not args.sets and not args.files:
                raise ValueError('Supply --set or --file')
            changes = []
            for value in args.sets:
                fact, sep, raw = value.partition('=')
                if not sep:
                    raise ValueError('Use --set fact=JSON-scalar')
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
                changes.append({'fact': fact, 'value': parsed})
            files = {repo_path(p): (Path(args.repo) / p).read_text(encoding='utf-8') for p in args.files}
            result = check_proposal(client, changes=changes or None, files=files or None)
        except (ValueError, OSError, GraphUnavailable) as exc:
            print(json.dumps({'verdict': 'ERROR', 'error': str(exc)}))
            return 1
        print(json.dumps(result, indent=2))
        return {'BLOCKED': 2, 'NEEDS_REVIEW': 1, 'ERROR': 1, 'CLEAR_WITHIN_SCOPE': 0}[result['verdict']]
    if args.cmd == "serve":
        import uvicorn
        from .web.app import create_app
        from dataclasses import replace
        uvicorn.run(create_app(client,replace(s,graph_name=args.graph,falkordb_host=args.host,falkordb_port=args.port)),host=args.bind,port=args.web_port)
        return 0
    if args.cmd == "mcp":
        from .mcp_server import create_server
        create_server(client).run(transport="stdio")
        return 0
    if args.cmd in {"health","ask"}:
        from .graph.tools import GraphTools
        from .agent.analyst import answer_question
        tools=GraphTools(client)
        result=tools.call("guarantee_health",{}) if args.cmd=="health" else answer_question(tools,args.question,s)
        print(json.dumps(result,indent=2,default=str))
        return 0
    if args.cmd in {"assess","poll-once","reconcile"}:
        from .github.api import GitHub
        from .github.gitrepo import GitRepo
        from .github.poller import Pipeline
        github=GitHub(s.sandbox_repo,s.github_token)
        pipeline=Pipeline(client,github,GitRepo(s.sandbox_clone_dir,f"https://github.com/{s.sandbox_repo}.git"),s)
        try:
            if args.cmd=="poll-once":
                print(json.dumps([r.model_dump() for r in pipeline.once()],indent=2))
            elif args.cmd=="reconcile":
                print(json.dumps(pipeline.executor.reconcile(),indent=2))
            else:
                pipeline.sync_main()
                result=pipeline.assess_pr(args.pr,execute=args.execute)
                print(result.model_dump_json(indent=2))
                return 1 if result.verdict=="ERROR" else 0
        finally:
            github.close()
        return 0
    if args.cmd in {"demo","reset"}:
        from .github.store import Store
        # Local demo records are explicit synthetic PRs; never call GitHub or reset remote branches.
        if args.cmd=="reset":
            client.write("MATCH (a:Assessment)-[:OF]->(p:ChangeProposal) WHERE p.demo=true DETACH DELETE a")
            client.write("MATCH (p:ChangeProposal {demo:true}) DETACH DELETE p")
        ingest(client,s.sandbox_dir,"local-demo",f"https://github.com/{s.sandbox_repo}")
        data=load_scenarios("scenarios/scenarios.yaml")
        store=Store(client)
        for number,name in enumerate(["S1","S1_FIXED","S2","S12"],start=9001):
            result=run_scenario(client,Path(s.sandbox_dir),data["scenarios"][name],scenario_now(data))
            result.pr=f"pr:{number}"
            result.head_sha="local-demo-"+name
            pr={"number":number,"title":f"Local demo {name}: {data['scenarios'][name]['title']}","state":"open",
                "head":{"sha":result.head_sha,"ref":"demo/"+name,"repo":{"full_name":s.sandbox_repo}},
                "base":{"ref":"main","repo":{"full_name":s.sandbox_repo}}}
            aid=store.save(result,pr)
            client.write("MATCH (p:ChangeProposal {id:$id}) SET p.demo=true",{"id":result.pr})
            print(f"{name}: {result.verdict} {s.public_base_url}/assessments/{aid}")
        return 0
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
