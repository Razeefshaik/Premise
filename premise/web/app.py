from __future__ import annotations

import asyncio
import datetime as dt
import re
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from ..config import settings as get_settings
from ..graph.client import GraphClient, GraphUnavailable
from ..graph.tools import GraphTools
from ..graph.recorder import QueryRecorder
from ..reasoning.assess import graph_ready
from ..agent.analyst import answer_question
from ..agent.render import mermaid, provenance, render_comment
from ..github.store import Store
from ..reasoning.preflight import ChangeArgs, FileArgs
from ..reasoning.models import AssessmentResult, GuaranteeResult
from ..public_demo import PublicDemoMiddleware, PublicDemoDisabled, DISABLED, BANNER

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT/"templates"))
templates.env.filters['person_names'] = lambda ids, names: ', '.join(names.get(id, id) for id in ids)


def person_names(graph):
    """Names for presentation; graph identities and stored assessments stay unchanged."""
    return {row['id']: row['name'] for row in graph.read(
        'MATCH (p:Person) WHERE p.retired_rev IS NULL RETURN p.id AS id, p.name AS name')}


def attestation_evidence(graph, assumptions):
    ids = sorted({a["person"] for item in assumptions for a in item.attestations})
    names = {row["id"]: row["name"] for row in graph.read(
        "MATCH (p:Person) WHERE p.id IN $ids RETURN p.id AS id, p.name AS name", {"ids": ids})} if ids else {}
    def date(value):
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if value is not None else None
    return {item.id: [{**a, "name": names.get(a["person"], a["person"]),
                      "attested_on": date(a.get("on")), "review_date": date(a.get("review_by"))}
                     for a in item.attestations] for item in assumptions}


STATE_CLASSES = ('\n  classDef broken fill:#2a0f1a,stroke:#ff6b8b,color:#ffd3dd'
                 '\n  classDef unknown fill:#2a2310,stroke:#ffd27a,color:#fff0cc'
                 '\n  classDef holds fill:#0d2620,stroke:#7cf0c8,color:#d8fff2')


def coloured(text, guarantees):
    """Append state classes for the dark theme; guarantees are dicts with id, status and chain."""
    text += STATE_CLASSES
    for g in guarantees:
        nodes = ','.join(dict.fromkeys(re.sub(r'[^A-Za-z0-9_]', '_', node) for node in [g['id'], *g['chain']]))
        text += f"\n  class {nodes} {g['status'] if g['status'] in ('broken','holds') else 'unknown'}"
    if not guarantees and 'clear[' in text:
        text += '\n  class clear holds'
    return text


def scenario_presets(graph, keys=('S1','S1_FIXED','S6','S12')):
    from ..scenarios import load_scenarios
    facts = graph.named('registered_facts')
    lookup = {(f['file'],f['key']):f['id'] for f in facts}
    data = load_scenarios(Path(__file__).resolve().parents[2]/'scenarios/scenarios.yaml')
    return facts, [{'id':key,'title':data['scenarios'][key]['title'],
                    'values':{lookup[(p['file'],p['key'])]:p['value'] for p in data['scenarios'][key]['patches']
                              if p['op']=='set' and (p['file'],p['key']) in lookup}}
                   for key in keys]


def expiring_attestations(health, days=180):
    """Active attestations whose review date falls within the next `days`, soonest first (display only)."""
    now, horizon = health["now_ms"], health["now_ms"] + days * 86400000
    def label(ms):
        day = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)
        return f"{day.day} {day:%b %Y}"
    rows = [{"assumption": a["id"], "person": att["person"], "review_by": att["review_by"], "date": label(att["review_by"])}
            for a in health["assumptions"] for att in a["attestations"]
            if att.get("status") == "active" and att.get("review_by") is not None and now < att["review_by"] <= horizon]
    return sorted(rows, key=lambda r: r["review_by"])


class Question(BaseModel):
    question: str = Field(min_length=1,max_length=2000)


def create_app(client=None, config=None, *, graph_api_at_ms=None, graph_node_cap=300):
    s = config or get_settings()
    graph = client or GraphClient.from_settings(s)
    tools, store = GraphTools(graph), Store(graph)
    continuity_cache = {} if s.public_demo else None

    @asynccontextmanager
    async def lifespan(app):
        task, github = None, None
        if s.public_demo and graph_ready(graph)[0]:
            # Native descriptive algorithms run once at startup, never on a public request.
            from .continuity import projection
            revision = graph.named('graph_state')[0]
            for row in graph.read('MATCH (p:Person) WHERE p.retired_rev IS NULL RETURN p.id AS id'):
                analysis, queries = projection(graph, row['id'])
                continuity_cache[row['id']] = (revision, analysis, [{**q, 'recorded_at_startup': True} for q in queries])
        if s.poll_enabled and s.github_token:
            from ..github.api import GitHub
            from ..github.gitrepo import GitRepo
            from ..github.poller import Pipeline, poll
            github = GitHub(s.sandbox_repo,s.github_token)
            pipeline = Pipeline(graph,github,GitRepo(s.sandbox_clone_dir,f"https://github.com/{s.sandbox_repo}.git"),s)
            task = asyncio.create_task(poll(pipeline))
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if github:
            github.close()

    app = FastAPI(title="Premise", lifespan=lifespan,
                  docs_url=None if s.public_demo else '/docs', redoc_url=None if s.public_demo else '/redoc')
    app.state.public_demo = s.public_demo
    if s.public_demo:
        app.add_middleware(PublicDemoMiddleware)
        from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

        def public_docs(response):
            banner = f'<aside style="padding:12px;text-align:center;background:#17212b;color:white">{BANNER}</aside>'
            return HTMLResponse(response.body.decode().replace('<body>', '<body>' + banner))

        @app.get('/docs', include_in_schema=False)
        def docs():
            return public_docs(get_swagger_ui_html(openapi_url='/openapi.json', title='Premise API'))

        @app.get('/redoc', include_in_schema=False)
        def redoc():
            return public_docs(get_redoc_html(openapi_url='/openapi.json', title='Premise API'))

    @app.exception_handler(PublicDemoDisabled)
    async def disabled(request, exc):
        return JSONResponse({'detail': DISABLED}, status_code=403)
    from .graph_api import create_graph_router
    app.include_router(create_graph_router(graph, at_ms=graph_api_at_ms, node_cap=graph_node_cap))
    from .continuity import create_continuity_router
    app.include_router(create_continuity_router(graph, at_ms=graph_api_at_ms, startup_cache=continuity_cache))
    app.mount("/static",StaticFiles(directory=str(ROOT/"static")),name="static")

    @app.exception_handler(GraphUnavailable)
    async def unavailable(request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error":"Graph unavailable; ingest a ready revision before querying."},status_code=503)
        return templates.TemplateResponse(request=request,name="error.html",context={"message":"The company graph is unavailable. Start FalkorDB, then ingest the company repository."},status_code=503)

    @app.get("/healthz")
    def healthz():
        ready, rev, _ = graph_ready(graph)
        return JSONResponse({"ready":ready,"graph_rev":rev},status_code=200 if ready else 503)

    @app.get("/", response_class=HTMLResponse)
    def brain(request: Request):
        health = tools.call("guarantee_health",{})
        state = graph.named("graph_state")[0]
        import json
        facts, presets = scenario_presets(graph)
        plate = {"guarantees":[{k:g[k] for k in ("id","status","statement","prerequisites")} for g in health["guarantees"]],
                 "assumptions":[{k:a.get(k) for k in ("id","state","text","kind","lhs_fact","rhs_fact")} for a in health["assumptions"]],
                 "facts":[{k:f[k] for k in ("id","value","controlled_by")} for f in facts],"presets":presets}
        return templates.TemplateResponse(request=request,name="brain.html",context={"health":health,"state":state,
            "orphaned":tools.call("orphaned_decisions",{}),"recent":store.recent(),"plate":plate,"expiring":expiring_attestations(health),
            "warnings":json.loads(state["warnings_json"] or "[]"),"llm":s.llm_enabled,"provider":s.llm_provider})

    @app.post("/api/ask")
    def ask(payload:Question):
        return answer_question(tools,payload.question,s)

    @app.post('/api/check')
    def check_change(payload: ChangeArgs | FileArgs):
        with QueryRecorder(graph) as recorder:
            response = checked_change(payload)
            if isinstance(response, JSONResponse):
                import json
                return JSONResponse({**json.loads(response.body), 'queries': recorder.entries}, status_code=response.status_code)
            return {**response, 'queries': recorder.entries}

    def checked_change(payload):
        arguments = payload.model_dump(exclude_unset=True)
        if s.public_demo:
            if arguments.get('include_fixes'):
                raise PublicDemoDisabled()
            arguments['include_fixes'] = False
        try:
            result = tools.call('check_change' if isinstance(payload, ChangeArgs) else 'check_files',
                                arguments)
        except ValueError as exc:
            raise HTTPException(422, 'Invalid hypothetical proposal') from exc
        if any(r['code'] == 'R_UNTRACKED' for r in result['reasons']):
            return JSONResponse(result, status_code=422)
        if result['verdict'] == 'ERROR':
            return JSONResponse(result, status_code=503)
        visual = AssessmentResult(verdict=result['verdict'], guarantees=[GuaranteeResult(**g) for g in result['not_holding']])
        result['mermaid'] = coloured(mermaid(visual), result['not_holding'])
        result['names'] = {p['id']:p['name'] for p in graph.read('MATCH (p:Person) RETURN p.id AS id, p.name AS name')}
        return result

    @app.get('/what-if', response_class=HTMLResponse)
    def what_if(request: Request):
        tools.guard()
        facts, presets = scenario_presets(graph)
        return templates.TemplateResponse(request=request,name='whatif.html',context={'facts':facts,'presets':presets})

    @app.get('/explore', response_class=HTMLResponse)
    def explore(request: Request):
        tools.guard()
        return templates.TemplateResponse(request=request,name='explore.html',context={})

    @app.get("/api/health")
    def health():
        return tools.call("guarantee_health",{})

    @app.get('/benchmark', response_class=HTMLResponse)
    def benchmark(request: Request):
        return templates.TemplateResponse(request=request,name='benchmark.html',context={})

    @app.get('/continuity', response_class=HTMLResponse)
    def continuity(request: Request):
        return templates.TemplateResponse(request=request,name='continuity.html',context={})

    @app.get('/api/benchmark/questions')
    def benchmark_questions():
        from ..benchmark.run import dataset
        data, manifest = dataset()
        return {**data,'manifest':manifest,'queries':[]}

    @app.get('/api/benchmark')
    def benchmark_results():
        import json
        path = Path(__file__).resolve().parents[2] / 'bench/results/latest.json'
        if not path.exists():
            return JSONResponse({'error':'No recorded benchmark. Run premise bench run locally.','queries':[]},status_code=404)
        result = json.loads(path.read_text(encoding='utf-8'))
        return {**result,'recorded':True,'queries':result['setup_queries'][:1] +
                [q for row in result['rows'][:7] for q in row['queries']]}

    @app.get("/assessments/{aid}",response_class=HTMLResponse)
    def assessment(request:Request,aid:str):
        tools.guard()
        result = store.get(aid)
        if not result:
            raise HTTPException(404,"Assessment not found")
        ids = [c.fact for c in result.changed_facts]+[a.id for a in result.assumptions]+[g.id for g in result.guarantees]+[d.id for d in result.decisions]
        terms = sorted({word for c in result.changed_facts for word in re.findall(r"[a-zA-Z0-9]+", c.fact)
                        if len(word) > 2 and word not in {"hours", "seconds", "minutes"}})[:12]
        lexical_query = " | ".join(terms)
        search = graph.named("search_decision_passages",{"q":lexical_query}) if lexical_query else []
        lexical = sorted({r["decision"] for r in search})
        return templates.TemplateResponse(request=request,name="assessment.html",context={"result":result,"aid":aid,
            "mermaid":mermaid(result),"styled":coloured(mermaid(result),[g.model_dump() for g in result.guarantees if g.status != "holds"]),"sources":provenance(graph,ids),"lexical":lexical,"lexical_query":lexical_query,
            "attestations":attestation_evidence(graph,result.assumptions),
            "names":person_names(graph),
            "graph_only":sorted(set(d.id for d in result.decisions)-set(lexical))})

    @app.get("/api/assessments/{aid}")
    def assessment_json(aid:str):
        tools.guard()
        result=store.get(aid)
        if not result:
            raise HTTPException(404,"Assessment not found")
        return result.model_dump()

    @app.get("/entities/{id}",response_class=HTMLResponse)
    def entity(request:Request,id:str):
        resolved=tools.call("resolve",{"query":id,"limit":1})
        exact=next((r for r in resolved if r["id"]==id),None)
        if not exact:
            raise HTTPException(404,"Entity not found")
        labels=exact["labels"]
        data=tools.call("decision_lineage",{"id":id}) if "Decision" in labels else tools.call("guarantee_health",{"id":id}) if "Guarantee" in labels else tools.call("who_knows",{"id":id}) if "Service" in labels else tools.call("impact_if_broken",{"id":id}) if "Assumption" in labels else exact
        return templates.TemplateResponse(request=request,name="entity.html",context={"id":id,"data":data,"names":person_names(graph),"history":tools.call("recall",{"id":id}),"sources":provenance(graph,[id])})

    return app
