"""Single-worker entry point: seed bundled fixtures before accepting requests."""
import os
from pathlib import Path
import uvicorn
from .config import settings
from .graph.client import GraphClient
from .reasoning.assess import graph_ready
from .ingest.run import ingest
from .web.app import create_app


def prepare_graph(client, s):
    if not s.poll_enabled and not graph_ready(client)[0]:
        ingest(client,s.sandbox_dir,"local",f"https://github.com/{s.sandbox_repo}")
    if s.public_demo:
        # Persist only fixed, explicitly labelled fixture examples at startup. No GitHub.
        from .github.store import Store
        from .scenarios import load_scenarios, apply_patches, scenario_now
        from .reasoning.intake import overlay_from_files
        from .reasoning.assess import assess
        data = load_scenarios(Path(__file__).resolve().parents[1] / 'scenarios/scenarios.yaml')
        store = Store(client)
        revision = client.named('graph_state')[0]['rev']
        for number, name in enumerate(('S1', 'S1_FIXED', 'S2', 'S12'), 9001):
            sha = 'public-demo-v1-' + name
            existing = client.read('MATCH (a:Assessment {head_sha:$sha, graph_rev:$rev, public_seed_ready:true}) RETURN a.id AS id',
                                   {'sha': sha, 'rev': revision})
            if existing:
                continue
            facts, paths, model = overlay_from_files(client, apply_patches(Path(s.sandbox_dir), data['scenarios'][name]['patches']))
            result = assess(client, facts, changed_paths=paths, model_change=model, at_ms=scenario_now(data),
                            pr=f'pr:{number}', head_sha=sha, run_repair=False)
            aid = store.save(result, {'number': number, 'title': f'Local demo {name}: bundled fixture assessment',
                               'state': 'open', 'head': {'sha': sha, 'ref': 'demo/' + name, 'repo': {'full_name': s.sandbox_repo}},
                               'base': {'ref': 'main', 'repo': {'full_name': s.sandbox_repo}}})
            client.write('MATCH (p:ChangeProposal {id:$id}) SET p.demo=true', {'id': result.pr})
            client.write('MATCH (a:Assessment {id:$id}) SET a.public_seed_ready=true', {'id': aid})


def main():
    s=settings()
    client=GraphClient.from_settings(s)
    prepare_graph(client, s)
    # Never trust arbitrary X-Forwarded-For for IP limits. One worker owns the buckets.
    uvicorn.run(create_app(client,s),host="0.0.0.0",port=int(os.getenv('PORT', '8000')),proxy_headers=False)


if __name__=="__main__":
    main()
