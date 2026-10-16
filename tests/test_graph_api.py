from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from premise.config import Settings
from premise.graph.client import GraphClient, GraphUnavailable
from premise.graph.recorder import QueryRecorder
from premise.ingest.run import ingest
from premise.web.app import create_app
from premise.web.graph_api import EDGE_TYPES, GraphExplorer
from conftest import NOW, SANDBOX


def app(graph, cap=300):
    return create_app(graph, replace(Settings(), poll_enabled=False, llm_provider="none"),
                      graph_api_at_ms=NOW, graph_node_cap=cap)


def test_recorder_named_inline_write_nested_and_restore(new_graph):
    graph = new_graph()
    original = {name: getattr(graph, name) for name in ("read", "named", "write")}
    with QueryRecorder(graph) as outer:
        graph.write("CREATE (:GraphState {id:'state', rev:1, ingest_state:'ready'})")
        graph.named("graph_state")
        with QueryRecorder(graph) as inner:
            graph.read("RETURN $values AS values", {"values": list(range(35))})
        graph.read("RETURN 1 AS value")
    assert [q["name"] for q in outer.entries] == ["inline", "graph_state", "inline", "inline"]
    assert len(inner.entries) == 1 and len(inner.entries[0]["params"]["values"]) == 20
    assert outer.entries[0]["operation"] == "write" and outer.entries[1]["rows"] == 1
    assert all(q["ms"] >= 0 and isinstance(q["ms"], float) for q in outer.entries)
    assert all(getattr(graph, name) == original[name] for name in original)
    assert not any(name in graph.__dict__ for name in original)


def test_recorder_isolates_concurrent_calls_on_one_shared_client(kestrel):
    # Warm the lazy connection before starting concurrent requests.
    kestrel.named("graph_state")
    barrier = Barrier(2)
    def request(value):
        with QueryRecorder(kestrel) as recorder:
            barrier.wait(timeout=10)
            rows = kestrel.read("RETURN $value AS value", {"value": value})
            barrier.wait(timeout=10)
        return rows, recorder.entries
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(request, ["request A", "request B"]))
    for value, (rows, entries) in zip(["request A", "request B"], responses):
        assert rows == [{"value": value}]
        assert len(entries) == 1 and entries[0]["params"] == {"value": value}
    assert "read" not in kestrel.__dict__


def test_recorder_redacts_credentials_and_copies_params(kestrel):
    params = {"token": "sensitive-value", "nested": {"api_key": "secret"},
              "message": "Bearer private-value", "values": [1, 2]}
    with QueryRecorder(kestrel) as recorder:
        kestrel.read("RETURN $values AS values", params)
        params["values"].append(3)
    recorded = recorder.entries[0]["params"]
    assert recorded["token"] == "[redacted]" and recorded["nested"]["api_key"] == "[redacted]"
    assert recorded["message"] == "[redacted]" and recorded["values"] == [1, 2]
    assert "sensitive-value" not in str(recorder.entries)


def test_recorder_restores_methods_and_records_failed_queries(kestrel):
    original = kestrel.read
    with pytest.raises(Exception):
        with QueryRecorder(kestrel) as recorder:
            kestrel.read("THIS IS INVALID CYPHER")
    assert kestrel.read == original and "read" not in kestrel.__dict__
    assert recorder.entries[0]["rows"] == 0 and recorder.entries[0]["error"]


def test_overview_has_engine_health_all_guarantees_and_real_query_timings(kestrel):
    with TestClient(app(kestrel)) as http:
        response = http.get("/api/graph/overview")
        assert response.status_code == 200, response.text
        data = response.json()
        guarantees = {n["id"]: n for n in data["nodes"] if n["label"] == "Guarantee"}
        assert len(guarantees) == 9
        assert guarantees["G_RATES_FRESH"]["health"] == "unknown"
        assert guarantees["G_DEDUPE"]["health"] == "holds" and guarantees["G_DEDUPE"]["tier"] == 1
        assert guarantees["G_DEDUPE"]["pagerank"] > 0
        assert {e["type"] for e in data["edges"]} <= {"PROVIDES", "RELIES_ON", "REQUIRES"}
        assert data["graph_rev"] == 1 and data["queries"] and not data["truncated"]
        assert all(q["operation"] == "read" and q["ms"] >= 0 for q in data["queries"])
        assert not data["health_cache"]["hit"]
        cached = http.get("/api/graph/overview").json()
        assert cached["health_cache"]["hit"]
        assert not any(q["name"] == "evaluate_assumptions" for q in cached["queries"])
        assert cached["queries"]  # cache hits report actual request queries, never old timings


def test_neighborhood_depths_kinds_cap_and_injection_boundaries(kestrel):
    with TestClient(app(kestrel)) as http:
        previous = set()
        for depth in range(1, 5):
            response = http.get("/api/graph/neighborhood", params={"focus": "G_DEDUPE", "depth": depth})
            assert response.status_code == 200, response.text
            data = response.json()
            ids = {n["id"] for n in data["nodes"]}
            assert previous <= ids and "G_DEDUPE" in ids
            previous = ids
            assert any(q["name"] == f"explore_neighborhood_d{depth}" for q in data["queries"])
            assert all(e["type"] in EDGE_TYPES for e in data["edges"])
            assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])
        for depth in (0, 5, "1] DELETE n", "1.5"):
            assert http.get("/api/graph/neighborhood", params={"focus": "G_DEDUPE", "depth": depth}).status_code == 422
        data = http.get("/api/graph/neighborhood", params={"focus": "G_DEDUPE", "depth": 4, "kinds": "reasoning,facts"}).json()
        assert not {n["label"] for n in data["nodes"]} & {"Person", "Team", "Service"}
        assert http.get("/api/graph/neighborhood", params={"focus": "G_DEDUPE", "kinds": "Assessment"}).status_code == 422
        unknown = http.get("/api/graph/node/G_ABSENT")
        assert unknown.status_code == 404 and unknown.json()["error"] == "unknown_entity"
        assert unknown.json()["queries"]
    with TestClient(app(kestrel, cap=3)) as http:
        data = http.get("/api/graph/neighborhood", params={"focus": "G_DEDUPE", "depth": 4}).json()
        assert data["truncated"] and len(data["nodes"]) == 3
        assert data["nodes"][0]["id"] == "G_DEDUPE"
        assert [(n["distance"], -n["pagerank"], n["id"]) for n in data["nodes"]] == sorted(
            (n["distance"], -n["pagerank"], n["id"]) for n in data["nodes"])
    explorer = GraphExplorer(kestrel)
    for depth in (True, 0, 5, "2"):
        with pytest.raises(ValueError):
            explorer.neighborhood("G_DEDUPE", depth, "reasoning", {})


def test_path_uses_bounded_minimum_hops_and_node_evidence(kestrel):
    with TestClient(app(kestrel)) as http:
        response = http.get("/api/graph/path", params={"from": "ADR-012", "to": "A_RETRY_WINDOW"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["path"][0] == "ADR-012" and data["path"][-1] == "A_RETRY_WINDOW"
        assert "G_DEDUPE" in data["path"]
        assert {n["id"] for n in data["nodes"]} == set(data["path"])
        assert len(data["edges"]) == len(data["path"]) - 1
        for id in ("ADR-012", "G_DEDUPE", "A_RETRY_WINDOW", "paymentservice", "p_jun", "paylane.retry_window_hours"):
            detail = http.get("/api/graph/node/" + id)
            assert detail.status_code == 200, detail.text
            assert detail.json()["node"]["id"] == id and detail.json()["queries"]
        detail = http.get("/api/graph/node/G_DEDUPE").json()
        assert detail["evidence"] and all(e["line"] for e in detail["evidence"])
        assert "p_anika" in detail["reviewers"] and detail["owners"]
        absent = http.get("/api/graph/path", params={"from": "ADR-012", "to": "A_ABSENT"})
        assert absent.status_code == 404


def test_disconnected_unknown_operational_and_not_ready_graphs(new_graph):
    graph = new_graph()
    ingest(graph, SANDBOX, "api-test")
    graph.write("CREATE (:Entity:Service {id:'isolated', name:'Isolated'})")
    graph.write("CREATE (:Entity:Assessment {id:'private-assessment', title:'Internal'})")
    with TestClient(app(graph)) as http:
        data = http.get("/api/graph/path", params={"from": "isolated", "to": "ADR-012"}).json()
        assert data["path"] is None
        for path in ("/api/graph/node/private-assessment", "/api/graph/neighborhood?focus=private-assessment"):
            assert http.get(path).status_code == 404
        graph.write("MATCH (s:GraphState) SET s.ingest_state='loading'")
        response = http.get("/api/graph/overview")
        assert response.status_code == 503 and response.json()["queries"]
    with TestClient(app(new_graph())) as http:
        assert http.get("/api/graph/overview").status_code == 503


def test_fifty_api_calls_do_not_mutate_the_graph(kestrel, monkeypatch):
    counts = ("MATCH (n) RETURN count(n) AS nodes", "MATCH ()-[r]->() RETURN count(r) AS edges")
    before, state = [kestrel.read(q) for q in counts], kestrel.named("graph_state")
    def forbidden(*a, **kw):
        pytest.fail("Graph API attempted a write")
    monkeypatch.setattr(kestrel, "write", forbidden)
    with TestClient(app(kestrel)) as http:
        paths = ["/api/graph/overview", "/api/graph/neighborhood?focus=G_DEDUPE&depth=2",
                 "/api/graph/path?from=ADR-012&to=A_RETRY_WINDOW", "/api/graph/node/G_DEDUPE", "/api/graph/node/ADR-012"]
        for n in range(50):
            response = http.get(paths[n % len(paths)])
            assert response.status_code == 200, response.text
    assert [kestrel.read(q) for q in counts] == before and kestrel.named("graph_state") == state


def test_health_cache_invalidates_on_revision_and_attestation_expiry(new_graph):
    graph = new_graph()
    ingest(graph, SANDBOX, "first")
    explorer = GraphExplorer(graph, at_ms=NOW)
    first = explorer.execute(explorer.overview)
    assert not first["health_cache"]["hit"]
    explorer.tools.at_ms = 1803945600000  # 2027-03-02 UTC
    later = explorer.execute(explorer.overview)
    assert not later["health_cache"]["hit"]
    assert next(n for n in later["nodes"] if n["id"] == "G_DEDUPE")["health"] == "unknown"
    ingest(graph, SANDBOX, "second")
    revised = explorer.execute(explorer.overview)
    assert revised["graph_rev"] != first["graph_rev"] and not revised["health_cache"]["hit"]
