"""Local review surface. GETs never mutate; Dismiss writes only staging rejection memory."""
from __future__ import annotations

from collections import Counter
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from premise.graph.client import GraphUnavailable
from ..registry import Ext
from ..staging import Staging, now_ms

HERE = Path(__file__).parent
KINDS = {"drift": "Fact changes", "challenge": "Attestation challenges", "identity": "Identity proposals",
         "knowledge": "Knowledge proposals", "unmatched": "Unmatched mentions", "decision": "Decision drafts"}


def loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def private_allowed(request, bind):
    # Forwarded headers are never evidence of a local connection.
    return (loopback(bind) and request.client is not None and loopback(request.client.host)
            and loopback(request.url.hostname))


def age(at):
    if not at:
        return "Age unavailable"
    seconds = max(0, (now_ms() - at) // 1000)
    return "Just now" if seconds < 60 else f"{seconds // 60} min ago" if seconds < 3600 else f"{seconds // 3600} h ago"


def evidence_of(row):
    data = row.get("data", {})
    return data.get("evidence") or json.loads(row.get("evidence_json") or "[]")


def items(staging):
    collected = {r["key"]: r for r in staging.review_items()}
    collected.update({r["key"]: r for r in staging.proposals()})
    unmatched = staging.c.read("MATCH (u:UnmatchedMention) WHERE u.active=true RETURN properties(u) AS u")
    for r in unmatched:
        u = r["u"]
        key = "unmatched:" + u["id"]
        collected[key] = {"key": key, "kind": "unmatched", "title": u["phrase"], "data": {"evidence": [u]},
                          "created_ms": u.get("created_ms"), "support": "observed"}
    visible = []
    for row in collected.values():
        rejection = staging.rejection(row["key"])
        newest = max((e.get("as_of_ms") or e.get("time_ms") or 0 for e in evidence_of(row)), default=0)
        if rejection and newest <= rejection["at_ms"]:
            continue
        visible.append(row)
    return visible


def summary(row, local):
    data, kind = row.get("data", {}), row.get("kind", "drift")
    private = any(e.get("visibility") != "public" for e in evidence_of(row))
    title = row.get("title") or row["key"]
    if private and not local:
        title = {"unmatched": "Private relation mention", "decision": "Private decision evidence"}.get(kind, title)
    return {"key": row["key"], "url": "/item/" + quote(row["key"], safe=""), "kind": kind, "title": title,
            "support": row.get("support") or data.get("support") or "Review proposal",
            "contested": bool(row.get("contested") or data.get("contested")),
            "age": age(row.get("created_ms")), "private": private}


def create_app(staging: Staging, decision, knowledge, model_root, bind="127.0.0.1"):
    if len({staging.c.graph_name, decision.graph_name, knowledge.graph_name}) != 3:
        raise ValueError("review graphs must be distinct")
    app = FastAPI(title="Premise v2 review", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    secret = secrets.token_bytes(32)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin", "Content-Security-Policy":
            "default-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @app.exception_handler(GraphUnavailable)
    async def unavailable(request, exc):
        return HTMLResponse("Cannot reach FalkorDB. Start it, then reload this page.", status_code=503)

    def render(request, template, **context):
        nonce = request.cookies.get("v2_review", "") or secrets.token_urlsafe(24)
        token = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
        response = templates.TemplateResponse(request=request, name=template, context={"csrf": token, **context})
        response.set_cookie("v2_review", nonce, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
        return response

    @app.get("/", response_class=HTMLResponse)
    def queue(request: Request):
        local = private_allowed(request, bind)
        rows = [summary(r, local) for r in items(staging)]
        groups = [(label, [r for r in rows if r["kind"] == kind]) for kind, label in KINDS.items()]
        return render(request, "queue.html", groups=groups, count=len(rows), local=local)

    @app.get("/item/{key:path}", response_class=HTMLResponse)
    def detail(key: str, request: Request):
        row = next((r for r in items(staging) if r["key"] == key), None)
        if row is None:
            raise HTTPException(404, "This review item is no longer in the queue.")
        local = private_allowed(request, bind)
        data, evidence = row.get("data", {}), evidence_of(row)
        shown = []
        for e in evidence:
            visible = local or e.get("visibility") == "public"
            shown.append({"quote": e.get("quote") or e.get("data", {}).get("quote", "") if visible else
                          "(private source; quote withheld)",
                          "account": e.get("account") or e.get("person") or "Unknown account",
                          "item": e.get("envelope_key") or e.get("item") or ""})
        preview = json.loads(row.get("preview_json") or "{}")
        safe_body = local or evidence and all(e.get("visibility") == "public" for e in evidence) or row.get("kind") == "identity"
        url = row.get("pr_url") or data.get("issue_url")
        if url and urlsplit(url).scheme not in {"http", "https"}:
            url = None
        return render(request, "detail.html", item=summary(row, local), evidence=shown,
                      origins=data.get("origins") or json.loads(row.get("origins_json") or "[]"),
                      preview=preview.get("verdict") or row.get("verdict_preview") or "Not available",
                      body=(row.get("body") or data.get("body") or "") if safe_body else "Private details withheld.",
                      diff=row.get("diff", "") if safe_body else "", pr_url=url, local=local)

    @app.get("/relations", response_class=HTMLResponse)
    def relations(request: Request):
        local = private_allowed(request, bind)
        ext = Ext.load(model_root)
        try:
            usage = {r["name"]: r["n"] for r in knowledge.read("MATCH ()-[r]->() RETURN type(r) AS name, count(r) AS n")}
        except GraphUnavailable:
            usage = None
        examples = staging.c.read("MATCH (e:Extraction)-[:CITES]->(i:Item) WHERE e.grounded=true "
            "AND e.extractor IN ['K2','K2_LLM'] AND e.sequence=i.sequence AND NOT i.deleted "
            "RETURN e.data_json AS data, i.visibility AS visibility")
        rows = []
        for relation in ext.relations.get("relations", []):
            matches = [json.loads(e["data"])["quote"] for e in examples
                       if (local or e["visibility"] == "public") and json.loads(e["data"]).get("relation") == relation["name"]]
            rows.append({**relation, "usage": usage.get(relation["name"], 0) if usage is not None else "Unavailable",
                         "examples": matches[:3]})
        phrases = Counter()
        for r in staging.c.read("MATCH (u:UnmatchedMention) WHERE u.active=true RETURN u.phrase AS phrase, u.visibility AS visibility"):
            phrases[r["phrase"] if local or r["visibility"] == "public" else "(private phrase withheld)"] += 1
        return render(request, "relations.html", relations=rows, phrases=sorted(phrases.items()), local=local)

    @app.post("/item/{key:path}/dismiss")
    async def dismiss(key: str, request: Request):
        body = await request.body()
        nonce = request.cookies.get("v2_review", "")
        token = parse_qs(body.decode("utf-8", errors="replace")).get("csrf", [""])[0]
        expected = hmac.new(secret, nonce.encode(), hashlib.sha256).hexdigest()
        origin = request.headers.get("origin")
        if (len(body) > 4096 or not nonce or not hmac.compare_digest(token, expected)
                or origin and urlsplit(origin).netloc != request.url.netloc):
            raise HTTPException(403, "Reload the review item and try Dismiss again.")
        row = next((r for r in items(staging) if r["key"] == key), None)
        if row is None:
            raise HTTPException(404, "This review item is no longer in the queue.")
        staging.reject(key, row.get("fact", key), row.get("value", ""), "dismissed in review page")
        return RedirectResponse("/", status_code=303)

    return app
