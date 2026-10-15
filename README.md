# Premise

Premise checks every change against the guarantees your engineering decisions depend on. It is built on FalkorDB
for WeMakeDevs x FalkorDB Graph Hacks (Track 3 Company Brain, Track 1 Agents That Act on Connected Data).

Decisions (ADRs) declare the guarantees they provide and the guarantees they rely on. Each guarantee declares what it
requires: other guarantees and assumptions. Assumptions are either predicates over configuration facts in the repo, or
manual statements that hold only while a person who still works here has attested them. When a change touches a fact,
Premise evaluates every prerequisite of every affected guarantee in FalkorDB, propagates failures through guarantee
requirements only, finds the decisions that promise or rely on a broken guarantee, routes review to someone still
accountable, and searches for a fix that it verifies against the graph.

**Status (Oct 16, 03:45 IST):** milestone 1 done: graph model, seeded company, ingestion, assumption evaluator,
guarantee propagation, routing, verdict policy, deterministic fix search. 47 of 47 tests pass on FalkorDB 4.18.3.
GitHub actions, the LLM agent, MCP, and the UI are later milestones. The full specification is in
[docs/Premise_Implementation_Spec.md](docs/Premise_Implementation_Spec.md).

## Run it

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Tests: uses FALKORDB_PORT if a server is running there, otherwise starts the FalkorDB module from the
# falkordblite wheel as a real redis-server process.
pytest -q

# Against a running FalkorDB (for example: docker run -p 6379:6379 -p 3000:3000 falkordb/falkordb)
premise --port 6379 ingest --repo sandbox/kestrel-platform
premise --port 6379 scenarios
premise --port 6379 assess-scenario S1
```

## Layout

| Path | What it is |
| --- | --- |
| `sandbox/kestrel-platform/` | The fictional company as code (published separately as the PR sandbox repo) |
| `scenarios/scenarios.yaml` | Ground truth: file patches like a pull request, and what Premise must find |
| `premise/graph/queries/*.cypher` | Every Cypher query the product depends on |
| `premise/ingest/` | Deterministic parsing with line numbers, validation, revisioned loading |
| `premise/reasoning/` | Evaluation set, assumption evaluation, rollup, impact, routing, policy, fix search |
| `tests/` | Real FalkorDB tests, including one per review correction |

## AI assistance

Design and code were written with an AI coding assistant (Claude) and reviewed and run by the author. The synthetic
company data is fictional.
