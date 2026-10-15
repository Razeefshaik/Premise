from __future__ import annotations

import asyncio
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
from ..reasoning.assess import graph_ready
from ..agent.analyst import answer_question
from ..agent.render import mermaid, provenance, render_comment
from ..github.store import Store

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT/"templates"))


class Question(BaseModel):
    question: str = Field(min_length=1,max_length=2000)


def create_app(client=None, config=None):
    s = config or get_settings()
    graph = client or GraphClient(s.falkordb_host,s.falkordb_port,s.graph_name)
    tools, store = GraphTools(graph), Store(graph)

    @asynccontextmanager
    async def lifespan(app):
        task, github = None, None
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

    app = FastAPI(title="Premise", lifespan=lifespan)
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
        return templates.TemplateResponse(request=request,name="brain.html",context={"health":health,"state":state,
            "orphaned":tools.call("orphaned_decisions",{}),"recent":store.recent(),
            "warnings":json.loads(state["warnings_json"] or "[]"),"llm":bool(s.anthropic_api_key)})

    @app.post("/api/ask")
    def ask(payload:Question):
        return answer_question(tools,payload.question,s)

    @app.get("/api/health")
    def health():
        return tools.call("guarantee_health",{})

    @app.get("/assessments/{aid}",response_class=HTMLResponse)
    def assessment(request:Request,aid:str):
        tools.guard()
        result = store.get(aid)
        if not result:
            raise HTTPException(404,"Assessment not found")
        ids = [c.fact for c in result.changed_facts]+[a.id for a in result.assumptions]+[g.id for g in result.guarantees]+[d.id for d in result.decisions]
        search = graph.named("search_decision_passages",{"q":"retry | Paylane | window"}) if "paylane.retry_window_hours" in ids else []
        lexical = sorted({r["decision"] for r in search})
        return templates.TemplateResponse(request=request,name="assessment.html",context={"result":result,"aid":aid,
            "mermaid":mermaid(result),"sources":provenance(graph,ids),"lexical":lexical,
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
        return templates.TemplateResponse(request=request,name="entity.html",context={"id":id,"data":data,"history":tools.call("recall",{"id":id}),"sources":provenance(graph,[id])})

    return app
