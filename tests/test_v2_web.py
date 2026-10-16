import json
import re

from fastapi.testclient import TestClient
import pytest

from conftest import SANDBOX
from premise_v2.staging import Staging
from premise_v2.web import create_app

SECRET = "Private incident quote 124923"


def setup(new_graph, bind="127.0.0.1"):
    stage, decision, knowledge = new_graph(), new_graph(), new_graph()
    staging = Staging(stage)
    staging.setup()
    knowledge.write("CREATE (:KnowledgeState {status:'ready'})")
    evidence = [{"quote": SECRET, "visibility": "private", "account": "slack:U1", "envelope_key": "slack:X"}]
    staging.upsert_proposal("review:test", {"kind": "drift", "title": "Review retry policy", "status": "open",
        "support": "corroborated", "contested": True, "evidence_json": json.dumps(evidence),
        "origins_json": json.dumps([["slack:X"], ["jira:X"]]), "body": SECRET, "diff": "+" + SECRET,
        "preview_json": json.dumps({"verdict": "BLOCKED"}), "pr_url": "https://github.com/example/repo/pull/1"})
    stage.write("CREATE (:UnmatchedMention {id:'unmatched1', phrase:$q, quote:$q, active:true, visibility:'private'})",
                {"q": SECRET})
    app = create_app(staging, decision, knowledge, SANDBOX, bind=bind)
    return app, staging, decision, knowledge


@pytest.mark.parametrize("bind,client,host,visible", [
    ("127.0.0.1", "127.0.0.1", "localhost", True),
    ("127.0.0.1", "::1", "localhost", True),
    ("127.0.0.1", "203.0.113.1", "localhost", False),
    ("127.0.0.1", "127.0.0.1", "public.example", False),
    ("0.0.0.0", "127.0.0.1", "localhost", False),
])
def test_review_renders_and_private_evidence_requires_local_server_client_and_host(new_graph, bind, client, host, visible):
    app, staging, decision, knowledge = setup(new_graph, bind)
    with TestClient(app, base_url=f"http://{host}", client=(client, 123)) as http:
        for path in ("/", "/item/review:test", "/relations"):
            response = http.get(path, headers={"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost"})
            assert response.status_code == 200
            if visible and path != "/":
                assert SECRET in response.text
            if not visible:
                assert SECRET not in response.text
        assert "BLOCKED" in http.get("/item/review:test").text


def test_dismiss_only_writes_rejection_and_removes_queue_item(new_graph, monkeypatch):
    app, staging, decision, knowledge = setup(new_graph)
    def forbidden(*a, **kw):
        pytest.fail("review page must not write decision or knowledge graphs")
    monkeypatch.setattr(decision, "write", forbidden)
    monkeypatch.setattr(knowledge, "write", forbidden)
    writes = []
    write = staging.c.write
    def tracked(cypher, params=None):
        writes.append(cypher)
        return write(cypher, params)
    monkeypatch.setattr(staging.c, "write", tracked)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 123)) as http:
        for path in ("/", "/relations", "/item/review:test"):
            response = http.get(path)
            assert response.status_code == 200
            assert response.headers["referrer-policy"] == "same-origin"
        assert not writes
        csrf = re.search(r'name="csrf" value="([^"]+)"', response.text)[1]
        assert http.post("/item/review:test/dismiss", data={"csrf": csrf}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert http.post("/item/review:test/dismiss", data={"csrf": "bad"}).status_code == 403
        response = http.post("/item/review:test/dismiss", data={"csrf": csrf},
                             headers={"Origin": "http://localhost"}, follow_redirects=False)
        assert response.status_code == 303 and staging.rejection("review:test")
        assert "Review retry policy" not in http.get("/").text
        assert http.get("/item/review:test").status_code == 404
        assert len(writes) == 1 and "Rejection" in writes[0]


def test_missing_knowledge_graph_is_reported_without_inventing_zero_counts(new_graph):
    stage, decision, knowledge = new_graph(), new_graph(), new_graph()
    staging = Staging(stage)
    staging.setup()
    with TestClient(create_app(staging, decision, knowledge, SANDBOX)) as http:
        assert "Unavailable" in http.get("/relations").text
        assert "No evidence waiting for review" in http.get("/").text


def test_dismissed_finding_returns_only_when_evidence_is_newer(new_graph):
    app, staging, decision, knowledge = setup(new_graph)
    staging.reject("review:test", "test", "", "dismissed", at_ms=1000)
    with TestClient(app) as http:
        assert "Review retry policy" not in http.get("/").text
        # Re-rendering the same finding doesn't create newer evidence.
        staging.upsert_proposal("review:test", {"title": "Review retry policy"})
        assert "Review retry policy" not in http.get("/").text
        evidence = [{"quote": "New public evidence", "visibility": "public", "as_of_ms": 1001}]
        staging.upsert_proposal("review:test", {"evidence_json": json.dumps(evidence)})
        assert "Review retry policy" in http.get("/").text


def test_v1_stylesheet_is_copied_and_bundled():
    from conftest import ROOT
    assert (ROOT / "premise_v2/web/static/style.css").read_bytes() == (ROOT / "premise/web/static/style.css").read_bytes()
