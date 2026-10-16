# V3 phase status

Design: [Premise_V3_Design.md](Premise_V3_Design.md). V3 is roadmap Phase A.
Each phase has its own branch and local commits. No V3 merge or push has been performed.

| Phase | Status | Branch |
| --- | --- | --- |
| V3.1 Query recorder + Graph API | Complete and verified locally | `v3/query-recorder-graph-api` |
| V3.2 Decision Explorer | Complete and batch verified | `v3/decision-explorer` |
| V3.3 Live consequences | Complete and batch verified | `v3/live-consequences` |
| V3.4 Benchmark | Complete and batch verified | `v3/benchmark` |
| V3.5 Red team | Implemented; 35/35 focused attacks passed | `v3/red-team` |
| V3.6 Continuity | Implemented; focused checks passed | `v3/continuity` |
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

## Batch workflow

The user authorized building three phases before each full regression/browser run.
Branches are stacked from the preceding V3 phase so the complete build stays isolated
from `main`; no automatic main merge or push is performed. Each phase still has its
own local commit. V3.2 is `720f993`; V3.3 is `0655b9f`.

V3.2 adds a pinned, locally vendored Cytoscape explorer, node evidence, depth/kind
controls, shift-click paths, keyboard-accessible node selection and a real query drawer.
V3.3 reuses `/api/check` for hypothetical changes, shows the four downstream guarantee
failures, merges the affected graph neighborhood and applies only engine-verified fixes.
No hypothetical data is written or posted to GitHub.

V3.4 freezes 60 authored questions and gold ids with a SHA-256 manifest before scoring.
All three systems use real FalkorDB. Vector retrieval uses the pinned MiniLM checkpoint
through CPU ONNX, downloaded once; `pip install -e ".[benchmark]"` installs optional
inference dependencies. Run `premise bench run --download-model` against an ingested
graph. Both retrieval systems use the same active ADR passages. All k values and both
splits are published, with a table/chart on `/benchmark` and caveats in
[BENCHMARK.md](BENCHMARK.md). CI replays recorded, real embeddings to test vector index
creation/query/cleanup without a model download; their provenance is stored with them.
The benchmark report uses actual local inference, not the test embedding fixture.

Focused benchmark integration checks: **3 passed**. Batch verification: **302 tests passed
in 266.36 seconds**, **12/12 scenarios passed**, and browser checks passed at desktop
1440×1050 and mobile 390×844 with no page/console errors. The browser exercised actual
node clicking, four red guarantees for S1, verified repair back to green, recorded Cypher
and the benchmark chart/table. Small later stylesheet refinements reuse the same controls;
their final captures will be included in the V3 finish review.

## V3.5 implementation

35 YAML-defined attacks exercise deterministic intake, PR metadata, comments, paths,
malformed/10 MB/deep/recursive YAML, attestations, analyst grounding, unknown entities,
forks, stale heads, outages and read-only tools. The runner publishes real JUnit outcomes
to [REDTEAM.md](REDTEAM.md); failures fail CI. GitHub and model output use existing fakes.
Bare-link and depth/alias regressions failed before the fixes and pass afterward.
Untrusted links are neutralized, mentions remain full-width, and company YAML is limited
to 200 KB, depth 64 and 20,000 parse events, with aliases explicitly unsupported.
The focused run passed **35/35**; full regression follows after V3.7.

## V3.6 implementation

`/continuity` simulates departure through optional `gone=[]` attestation/routing inputs.
Default arguments preserve existing behavior, including direct named-query callers.
The API reports newly orphaned accountability separately from decisions affected by
unknown guarantees: Anika leaving affects ADR-007 without falsely declaring it orphaned.
Native betweenness and WCC run on an owned, temporary bidirectional Person–Service–Decision
projection; it is deleted after the call. Team ownership connects current members to
services for descriptive analysis only. Algorithm scores do not change engine verdicts.
Focused tests: **2 passed**, including all twelve scenarios compared with explicit
`gone=[]`, source graph isolation, projection cleanup and Jun's replacement reviewers.
