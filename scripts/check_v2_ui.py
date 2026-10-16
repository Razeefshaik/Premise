"""Bounded desktop/mobile browser QA against isolated fixture graphs; no models or APIs."""
from pathlib import Path
import json
import os
import socket
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redis
import uvicorn
from playwright.sync_api import sync_playwright
from premise.config import settings
from premise.graph.client import GraphClient
from premise_v2.knowledge import load_knowledge
from premise_v2.pipeline import Pipeline, fixture_workers
from premise_v2.web import create_app


def main():
    s = settings()
    suffix = uuid.uuid4().hex[:10]
    clients = [GraphClient(s.falkordb_host, s.falkordb_port, f"premise_ui_{kind}_{suffix}") for kind in ("stage", "decision", "knowledge")]
    stage, decision, knowledge = clients
    r = redis.Redis(host=s.falkordb_host, port=s.falkordb_port)
    stream = "premise:ui:" + suffix
    server = thread = None
    try:
        p = Pipeline(r, stage, decision, s.sandbox_dir, fixture_workers("fixtures/v2"), stream_name=stream)
        p.run()
        if (Path(s.sandbox_dir) / "knowledge/relations.yaml").exists():
            load_knowledge(knowledge, decision, s.sandbox_dir, {s.graph_name, "premise_codex_demo"})
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(p.staging, decision, knowledge, s.sandbox_dir),
                                host="127.0.0.1", port=port, log_level="error", proxy_headers=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.1)
        if not server.started:
            raise RuntimeError("review server did not start")
        artifact = Path(".impeccable/review")
        artifact.mkdir(parents=True, exist_ok=True)
        binaries = [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
        executable = next((str(p) for p in binaries if p.exists()), None)
        errors, checks = [], []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            base = f"http://localhost:{port}"
            page.goto(base)
            item = page.locator("tbody a").first.get_attribute("href")
            for name, path in (("queue", "/"), ("item", item), ("relations", "/relations")):
                for size, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.goto(base + path).status == 200
                    assert page.locator("h1").is_visible()
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    if os.getenv("V2_UI_CAPTURE", "true") == "true":
                        page.screenshot(path=str(artifact / f"{name}-{size}.png"), full_page=True)
                    checks.append(f"{name}-{size}: render and overflow passed")
            page.goto(base + item)
            with page.expect_response(lambda response: response.url.endswith("/dismiss")) as response:
                page.get_by_role("button", name="Dismiss finding").click()
            assert response.value.status == 303, (response.value.status, response.value.text(),
                {"origin": response.value.request.headers.get("origin"),
                 "cookie_sent": bool(response.value.request.headers.get("cookie")),
                 "cookies": [{k: c[k] for k in ("name", "domain", "secure", "sameSite")}
                             for c in page.context.cookies()], "url": response.value.url})
            page.wait_for_url(base + "/")
            assert page.locator(f'a[href="{item}"]').count() == 0
            browser.close()
        report = {"checks": checks, "page_errors": errors, "dismiss": "passed",
                  "sources": "synthetic Phase 1 fixtures; real isolated FalkorDB; LLM_PROVIDER=none"}
        (artifact / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        assert not errors
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
        for client in clients:
            client.delete_graph()
        r.delete(stream, stream + ":dead", stream + ":failures")


if __name__ == "__main__":
    main()
