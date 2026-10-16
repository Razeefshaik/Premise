# V3 phase status

Design: [Premise_V3_Design.md](Premise_V3_Design.md). V3 is roadmap Phase A.
Each phase has its own branch and local commits. No V3 merge or push has been performed.

| Phase | Status | Branch |
| --- | --- | --- |
| V3.1 Query recorder + Graph API | Complete and verified locally | `v3/query-recorder-graph-api` |
| V3.2 Decision Explorer | Pending | `v3/decision-explorer` (planned) |
| V3.3 Live consequences | Pending | `v3/live-consequences` (planned) |
| V3.4 Benchmark | Pending | `v3/benchmark` (planned) |
| V3.5 Red team | Pending | `v3/red-team` (planned) |
| V3.6 Continuity | Pending | `v3/continuity` (planned) |
| V3.7 Time machine | Pending | `v3/time-machine` (planned) |
| V3.8 Public replay | Pending | `v3/public-replay` (planned) |

## V3.1 implementation

Started from `main` at `6fb78aa`. Design saved in `246461d`; implementation checkpoint
`6c60772`, followed by input/trace hardening and this verification record. The existing Cortex interface, deterministic reasoning engine, scenarios and
v2 extraction plane are preserved.

- [QueryRecorder](../premise/graph/recorder.py) temporarily wraps graph reads, named queries
  and writes. Context-local dispatch isolates overlapping requests on a shared client.
  Nested recorders work; original methods return after the final context, including errors.
  Named queries are recorded once at the read. Entries contain name, full Cypher, detached
  parameters, elapsed client milliseconds and row count. Sensitive parameter names and
  recognizable credential values are redacted; lists are capped at 20 entries, with their
  paths explicitly listed under `truncated_params`. Results themselves are not logged.
- [Graph API](../premise/web/graph_api.py) mounts on the existing FastAPI app. Every successful
  response includes `graph_rev`, `nodes`, `edges`, `truncated` and actual request `queries`.
  Unknown entities return 404, invalid input 422, and missing/loading/unreachable graphs 503.
  Invalid input executes no queries and returns an empty trace rather than invented timings.
- Only the documented labels and edge types participate. Operational records, source passages
  and v2 staging nodes cannot become exploration nodes. Node details reuse existing lineage,
  ownership/reviewer tools and provenance, with source file/line references.
- Guarantee and assumption health comes from one existing `GraphTools.guarantee_health` call
  per cached revision. The cache also expires across attestation activation/expiry and clock
  changes. Every response reports cache hit and original evaluation time. Cached health does
  not replay old queries/timings as if they ran in the current request.
- Guarantee tiers reuse `guarantee_impact`; PageRank is descriptive. Decisions expose their
  lifecycle and linked guarantees, with `health: null`: this phase adds no new aggregate
  decision-health rule. Services, people, teams and facts also have no inferred health.
- Neighborhood depth selects one of four fixed query files, with integer checks in both HTTP
  validation and the service. The 300-node cap orders by distance, descending guarantee
  PageRank, then id. A lower cap is available only through app/service construction for tests.

### API examples

Start the existing application normally after ingesting a ready model, then open:

```text
/api/graph/overview
/api/graph/neighborhood?focus=G_DEDUPE&depth=2&kinds=reasoning,services
/api/graph/path?from=ADR-012&to=A_RETRY_WINDOW
/api/graph/node/G_DEDUPE
```

Node details include evidence, owners, reviewers, lineage and the current failure/unknown
chain when one exists. The path field is an ordered list of ids, or `null` when no allowed
path of at most six hops exists. Edge source/target always preserve authored direction even
when the path is traversed in reverse. A node-to-itself path contains that node and no edges.
The Explorer and its Show Cypher drawer belong to V3.2; this phase supplies their data.

### Verified compatibility adjustment

The running Docker module reports `41803` (FalkorDB 4.18.3). It rejected the design's
undirected `shortestPath` form in `WITH`, with:

```text
FalkorDB does not currently support undirected shortestPath traversals
```

[explore_path.cypher](../premise/graph/queries/explore_path.cypher) instead matches only
whitelisted undirected paths of 0–6 hops and orders by hop count, then ids, before taking
one result. This keeps the requested minimum-hop semantics without a projection or writes.
It is suited to the small reasoning graph; bounded path enumeration can grow expensive
on a much denser graph and remains subject to the database's query timeout.

The server also requires `ORDER BY length(p)` before projecting `p` away. Both behaviors
were verified against real queries, including reverse, identical and disconnected endpoints.
The [official path function reference](https://docs.falkordb.com/cypher/functions.html)
documents the directed `WITH shortestPath(...)` form; the undirected limitation above is
from this runtime test, not an assumed capability.

### Verification

Tests use real FalkorDB, with no model or live GitHub calls. Browser/scenario validation
used a fresh `premise_v3_validation_<uuid>` graph and a temporary loopback server with
polling/model use disabled. The owned server and graph were removed afterward.

- Focused API/recorder checks: 11 passed.
- Full regression suite: **297 passed**, one existing warning, **200.80 seconds**.
- `python -m premise.cli --graph <isolated-graph> scenarios`: **12/12 passed**.
- `scripts/check_ui.py`: **passed** at desktop 1440×1050 and mobile 390×844;
  `page_errors: []`, `console_errors: []`, Mermaid SVG rendered, analyst fallback and
  what-if/fix controls worked. The existing checker now asserts console errors as well
  as uncaught page errors.
- Fifty Graph API calls preserve node/edge counts and all GraphState fields, with graph writes
  explicitly forbidden. Tests cover revision/attestation cache invalidation, strict input
  validation, node caps, evidence and simultaneous recorder contexts.

Browser artifacts and command logs are ignored under `.runtime/v3-validation/`.
One existing Starlette/httpx deprecation warning is unrelated to this phase.
