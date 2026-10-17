# Premise

**Search finds documents. Premise finds consequences.**

Premise is a pull request check for engineering decisions, built on FalkorDB. It connects
architecture decisions to the guarantees they promise, guarantees to the assumptions they
require, and assumptions to live config values and dated human attestations. When a pull
request changes a fact, FalkorDB traces what breaks, Premise blocks or passes the PR, names
the people who must review, and opens a fix PR only after verifying on the graph that the fix works.

**[Live replay](https://razeefshaik.github.io/Premise/)** ·
**[Real PR that went red, then green](#the-real-github-flow)** ·
**[Benchmark](#benchmark-what-does-structure-buy)** ·
**[Graph data model](#graph-data-model)** ·
**[Cypher and algorithms](#cypher-and-graph-algorithms)** ·
**Demo video:** _link added on submission_

Built for WeMakeDevs × FalkorDB Graph Hacks, entering **Track 1: Agents That Act on Connected
Data** and **Track 3: Company Brain**.

![A partner's retry window rises to 72 hours, the failure travels through the graph, and the verified fix heals it](docs/media/propagation.gif)

<sub>Recorded from the local Explorer against a real FalkorDB. [Record it again](scripts/record_propagation.py).</sub>

| Result | Evidence |
| --- | --- |
| **348 tests pass**, 12/12 scenarios match | [CI workflow](.github/workflows/tests.yml) runs them against FalkorDB v4.18.3 |
| **Graph F1 1.00** vs 0.46 vector RAG on change impact questions | [Synthetic benchmark with its limits](docs/BENCHMARK.md) |
| **35/35** red team attacks end in the expected safe outcome | [Red team report](docs/REDTEAM.md) |
| **0** verdicts decided by a language model | Verdicts are parameterized Cypher plus deterministic Python |

---

## The problem

A team decides "we deduplicate partner webhooks in Redis for 24 hours, because the partner
stops retrying after 24 hours". Three other decisions quietly build on that promise: charging
once, matching refunds, keeping the ledger consistent. Months later someone records that the
partner now retries for 72 hours. Every test passes. Nothing in those three decisions mentions
the partner, so search and code review never find them, and duplicate charges start.

Premise keeps the *reasons* behind decisions as a graph, so a change is checked against
everything that depends on it.

## What Premise does

1. **Traces consequences.** A changed fact makes an assumption false, and the failure travels
   up `REQUIRES` edges to every guarantee and decision that depends on it, even when their text
   never mentions the changed value.
2. **Acts on the pull request.** Posts a `premise/decisions` commit status (BLOCKED, NEEDS_REVIEW
   or CLEAR_WITHIN_SCOPE) and one comment with the broken chain, the evidence lines, the
   decisions checked and not affected, and the people who should review.
3. **Fixes only what it has verified.** A bounded repair search tests candidate fixes on the graph
   and opens a fix PR only when the complete remedy turns every affected guarantee green.
4. **Answers company brain questions** from the same graph: what still holds, who knows about
   this, what breaks if this person leaves, which promises expire next month.
5. **Stops coding agents before they edit.** An MCP server lets Claude Code or Codex ask
   Premise whether a change is safe before writing it.

## Try it

**In the browser, no install:** [razeefshaik.github.io/Premise](https://razeefshaik.github.io/Premise/).
On every push to `main`, [a workflow](.github/workflows/pages.yml) starts a fresh FalkorDB
v4.18.3, ingests the fictional company, records the real API responses and publishes them.
The replay is read only: "Ask the company" and PR assessment need the local app.

**Locally, the full app** (Docker Desktop with a Linux engine, no keys needed):

```bash
docker compose up --build -d
docker compose exec app premise demo
```

Open **http://localhost:8000** for Premise and **http://localhost:3000** for the FalkorDB
Browser. Full setup is in [Run locally](#run-locally).

## A tour in screenshots

**1. The company brain.** A fictional company, Kestrel: 12 tracked facts feed assumptions that
support 9 guarantees across its architecture decisions.

![Premise landing page with the 3D company brain](docs/media/01-landing.jpg)

**2. Change one fact.** The partner retry window goes from 24 to 72 hours. `A_RETRY_WINDOW`
is violated and the failure travels up the `REQUIRES` chain.

![Explorer tracing failure from A_RETRY_WINDOW through G_DEDUPE to G_CHARGE_ONCE](docs/media/02-propagation.png)

**3. The verdict.** BLOCKED: 4 guarantees broken, 4 decisions affected, review routed to
Anika Rao, Ravi Menon and Jun Park, people who are still at the company.

![BLOCKED verdict banner with reviewers and an Apply verified fix button](docs/media/03-blocked.png)

**4. The verified fix.** Raising the dedupe TTL alone would break the Redis maximum, so the
complete remedy raises both to 72 hours. Applying it turns every affected guarantee green.

![Explorer after the verified fix: CLEAR, every affected guarantee holds](docs/media/04-verified-fix.png)

**5. Every verdict shows its Cypher.** The Explorer records each query it ran, with timings,
row counts and parameters. This is the query that decides guarantee health:

![The rollup_guarantees Cypher query shown in the Explorer](docs/media/05-show-cypher.png)

**6. Time machine.** Move the date to 2 March 2027. No code changes, but Anika's attestation
behind `A_STABLE_EVENT_ID` expires, so `G_DEDUPE` and four more guarantees become *unknown*.

![Time machine forecast showing guarantees turning unknown after an attestation expires](docs/media/06-time-machine.png)

**7. When someone leaves.** A hypothetical departure shows accountability gaps, promises that
become unverified, the next reviewers, and FalkorDB betweenness for knowledge bridges.

![Continuity page for a hypothetical departure of Anika Rao](docs/media/07-continuity.png)

**8. The assessment record.** Every assessment is stored in FalkorDB with its reasons, the
changed facts and the shortest chain to each failure.

![Assessment page: BLOCKED with four R_BROKEN_T1 reasons and their chains](docs/media/09-assessment.png)

## How it works

```mermaid
flowchart LR
  D[Decision<br/>ADR-007] -- PROVIDES --> G1[Guarantee<br/>G_DEDUPE]
  D2[Decision<br/>ADR-012] -- RELIES_ON --> G1
  G2[Guarantee<br/>G_CHARGE_ONCE] -- REQUIRES --> G1
  G1 -- REQUIRES --> A[Assumption<br/>A_RETRY_WINDOW]
  A -- LHS --> F1[Fact<br/>paylane.retry_window_hours]
  A -- RHS --> F2[Fact<br/>webhook.dedupe_ttl_hours]
  G1 -- REQUIRES --> A2[Assumption<br/>A_STABLE_EVENT_ID]
  P[Person<br/>Anika Rao] -- ATTESTED --> A2
```

1. **Facts** are values in config files, ingested deterministically with their file and line.
2. **Assumptions** are predicates over two facts (`retry_window <= dedupe_ttl`) or a human
   attestation with a review date. An attestation only counts while it is current and the person is active.
3. **Guarantees** `REQUIRES` assumptions or other guarantees. `REQUIRES` is the only edge failure
   can travel along, so a broken assumption never leaks into unrelated decisions.
4. **Three valued logic.** A guarantee is *broken* if any prerequisite is violated, else *unknown*
   if any is unverifiable, else *holds*. Broken beats unknown beats holds. An expired attestation
   makes a guarantee unknown, never healthy.
5. **A pull request is an overlay.** Premise reads the changed values from the PR's own diff and
   evaluates them without mutating the main graph. The main graph changes only after merge.
6. **Every affected guarantee is judged on its full prerequisite closure**, not only the path
   the change touched, and sibling guarantees are evaluated before a decision is reported as unaffected.

```mermaid
sequenceDiagram
  participant Dev as Developer or agent
  participant GH as GitHub PR
  participant P as Premise
  participant DB as FalkorDB
  Dev->>GH: change paylane retry window to 72
  P->>GH: fetch the PR head and its merge base
  P->>DB: facts in the diff, touched assumptions
  P->>DB: three valued rollup over REQUIRES*1..6
  DB-->>P: G_DEDUPE broken via A_RETRY_WINDOW, and 3 more
  P->>DB: test candidate fixes on the overlay
  P->>GH: status BLOCKED, comment with chain and reviewers
  P->>GH: fix PR, only for a verified complete remedy
```

## The real GitHub flow

This ran on the fictional company's repository,
[Razeefshaik/kestrel-platform](https://github.com/Razeefshaik/kestrel-platform), on 16 October 2026 (times in IST):

| Time | Event | Evidence |
| --- | --- | --- |
| 12:25:59 | PR #1 "Record Paylane new 72 hour retry policy" is assessed: **failure**, `BLOCKED: G_CHARGE_ONCE is broken via G_CHARGE_ONCE -> G_DEDUPE -> A_RETRY_WINDOW` | [status on commit a2d6537](https://github.com/Razeefshaik/kestrel-platform/commit/a2d6537d62f8cd2e94d8a8e4ad4949329d25e4be) |
| 12:26:06 | Premise opens **fix PR #2** into PR #1's branch: `redis.max_ttl_hours = 72`, `webhook.dedupe_ttl_hours = 72`, "Graph-verified complete remedy" | [PR #2](https://github.com/Razeefshaik/kestrel-platform/pull/2) |
| 12:26:34 | The fix PR's own check: **success**, `CLEAR_WITHIN_SCOPE: 4 prerequisite assumptions checked` | [PR #2](https://github.com/Razeefshaik/kestrel-platform/pull/2) |
| 12:39:33 | A human merges the fix into PR #1's branch | [merge commit 7693573](https://github.com/Razeefshaik/kestrel-platform/commit/76935738b0279b1ee3f9985a10eaf7911cde961f) |
| 12:39:55 | PR #1 is re-assessed: **success**, every affected guarantee holds | [PR #1](https://github.com/Razeefshaik/kestrel-platform/pull/1) |

The PR comment is a single comment that Premise updates in place, so PR #1 now shows the
green version. The red result is kept in the commit status history linked above.
Screenshot 8 shows the same change assessed by the local demo. [PR #3](https://github.com/Razeefshaik/kestrel-platform/pull/3)
is a safe change (email retries within the provider budget) that passes.

Fixes and the original PRs are never merged automatically. Fork PRs never get fix branches.

## Graph data model

```mermaid
flowchart TB
  subgraph Reasoning
    Decision -- PROVIDES --> Guarantee
    Decision -- RELIES_ON --> Guarantee
    Guarantee -- REQUIRES --> Guarantee
    Guarantee -- REQUIRES --> Assumption
    Assumption -- LHS / RHS --> Fact
    Decision -- SUPERSEDES --> Decision
  end
  subgraph Accountability
    Person -- ATTESTED --> Assumption
    Person -- ACCOUNTABLE_FOR --> Decision
    Person -- MEMBER_OF --> Team
    Team -- OWNS --> Service
    Decision -- GOVERNS --> Service
    Guarantee -- ABOUT --> Service
    Service -- DEPENDS_ON --> Service
  end
  subgraph Provenance
    Decision -- STATED_IN --> Source
    Fact -- DEFINED_IN --> Source
    Passage -- PART_OF --> Source
    Person -- AUTHORED --> Source
    Passage -- MENTIONS --> Entity[Any entity]
  end
  subgraph Memory
    Assessment -- OF --> ChangeProposal
    ChangeProposal -- CHANGES --> Fact
    Assessment -- FOUND / FLAGGED --> Guarantee
  end
```

Every domain node has an `Entity` label and a fulltext-searchable description. Derived
health is computed on demand; only authored decision lifecycle is stored on domain nodes.
Historical assessments store their result snapshots for audit.

| Nodes | Purpose |
| --- | --- |
| Decision, Guarantee, Assumption, Fact | Reasoning model and tracked configuration |
| Person, Team, Service | Accountability, ownership, expertise and service exposure |
| Source, Passage | Exact source commits, paths, lines, text and mentions |
| GraphState, ChangeProposal, Assessment, Action | Revisions, cursors, overlays, audit and execution memory |
| LLMCache | Request-hashed provider response replay; contains no API keys |

| Relationships | Meaning |
| --- | --- |
| PROVIDES, RELIES_ON | A decision promises or depends on a specific guarantee |
| REQUIRES | The only failure-propagation edge; AND semantics, acyclic, depth ≤6 |
| LHS, RHS, ATTESTED | Predicate operands and dated attestation by an active person |
| GOVERNS, ABOUT, DEPENDS_ON | Decision/service scope and caller exposure up to three hops |
| ACCOUNTABLE_FOR, MEMBER_OF, OWNS | Authored accountability and current ownership |
| STATED_IN, DEFINED_IN, PART_OF, AUTHORED, MENTIONS | Source provenance and deterministic text mentions |
| SUPERSEDES | Decision lifecycle linkage; superseded decisions never gate |
| CHANGES, OF, FOUND, FLAGGED, TOOK | Assessment and action history; never revision-swept |

Review routing prefers active authors and approvers. Otherwise active members of the current
owning team rank by distinct recent authored sources, then by ID.

## Cypher and graph algorithms

The verdict is a graph traversal. This is the query that decides guarantee health
([rollup_guarantees.cypher](premise/graph/queries/rollup_guarantees.cypher)):

```cypher
// Three valued AND over every prerequisite of each guarantee.
// broken if any reachable assumption is violated, else unknown if any is unknown, else holds.
// The witness is the shortest chain to a violated assumption if one exists, else to an unknown one.
UNWIND $guarantees AS gid
MATCH (g:Guarantee {id: gid})
OPTIONAL MATCH p = (g)-[:REQUIRES*1..6]->(a:Assumption)
WHERE a.id IN $violated OR a.id IN $unknown
WITH g, p, CASE WHEN a IS NULL THEN 2 WHEN a.id IN $violated THEN 0 ELSE 1 END AS rank
ORDER BY rank, length(p)
WITH g, collect(rank) AS ranks, head(collect(p)) AS witness
RETURN g.id AS guarantee, g.statement AS statement,
       CASE WHEN 0 IN ranks THEN 'broken' WHEN 1 IN ranks THEN 'unknown' ELSE 'holds' END AS status,
       CASE WHEN witness IS NULL THEN [] ELSE [n IN nodes(witness) | n.id] END AS chain
ORDER BY guarantee
```

Ranking each path (0 violated, 1 unknown, 2 fine) and sorting by rank then length gives both
the three valued result and the shortest witness chain in one query. That chain is what the
PR comment, the assessment page and the Explorer animation show.

All query arguments are parameters. Read tools use `GRAPH.RO_QUERY`; no user or LLM
input is executed as Cypher. Authored schema writes and operational memory writes are
fixed in the ingestor and store; their vocabulary cannot be selected by a model.

| Query | Responsibility |
| --- | --- |
| [graph_state](premise/graph/queries/graph_state.cypher) | Ready revision and main SHA |
| [facts_in_files](premise/graph/queries/facts_in_files.cypher) | Registered facts in the PR diff |
| [facts_by_id](premise/graph/queries/facts_by_id.cypher) | Fact values, control, paths and lines |
| [touched_assumptions](premise/graph/queries/touched_assumptions.cypher) | Inputs touched by the overlay |
| [guarantee_assumption_pairs](premise/graph/queries/guarantee_assumption_pairs.cypher) | Upward impact and complete downward prerequisites |
| [siblings](premise/graph/queries/siblings.cypher) | Related guarantees requiring independent evaluation |
| [evaluate_assumptions](premise/graph/queries/evaluate_assumptions.cypher) | Numeric/string predicates and current attestations |
| [rollup_guarantees](premise/graph/queries/rollup_guarantees.cypher) | Three-valued AND and shortest witness paths |
| [guarantee_impact](premise/graph/queries/guarantee_impact.cypher) | Accepted decisions, tiers, services and callers |
| [route_decision](premise/graph/queries/route_decision.cypher) | Review routing and evidence counts |
| [load_bearing_guarantees](premise/graph/queries/load_bearing_guarantees.cypher) | FalkorDB PageRank; display order only |
| [search_decision_passages](premise/graph/queries/search_decision_passages.cypher) | Lexical-gap baseline |
| [resolve](premise/graph/queries/resolve.cypher) | Fulltext entity resolution |
| [decision_lineage](premise/graph/queries/decision_lineage.cypher) | Requirements and facts supporting a decision |
| [who_knows](premise/graph/queries/who_knows.cypher) | Current service owners and evidence-ranked experts |
| [search_evidence](premise/graph/queries/search_evidence.cypher) | Source-grounded passage search |
| [evidence_sources](premise/graph/queries/evidence_sources.cypher) | Authored source citations |
| [orphaned_decisions](premise/graph/queries/orphaned_decisions.cypher) | Accountability gaps |
| [recall](premise/graph/queries/recall.cypher) | Historical assessments by entity |

**FalkorDB features used, and where:**

| Feature | Used for | Where |
| --- | --- | --- |
| Variable length paths `[:REQUIRES*1..6]` | Failure propagation and witness chains | [rollup_guarantees](premise/graph/queries/rollup_guarantees.cypher) |
| `algo.pageRank('Guarantee', 'REQUIRES')` | Ordering "What still holds?" by how load bearing a guarantee is | [load_bearing_guarantees](premise/graph/queries/load_bearing_guarantees.cypher) |
| `algo.betweenness`, `algo.WCC` | Knowledge bridges and disconnection when a person leaves | [continuity.py](premise/web/continuity.py) |
| Fulltext index | Resolving names like "Paylane" or "ADR-012" to entities | [resolve](premise/graph/queries/resolve.cypher) |
| Vector index, `db.idx.vector.queryNodes` (cosine) | The vector RAG baseline in the benchmark, on the same database | [premise/benchmark](premise/benchmark) |
| `GRAPH.RO_QUERY` | Every read tool used by the MCP server, Analyst and web app | [premise/graph](premise/graph) |
| Redis Streams next to the graph | The v2 ingestion stream (XADD, consumer groups, XAUTOCLAIM) | [premise_v2/stream.py](premise_v2/stream.py) |

FalkorDB is the only datastore. It also holds graph revisions, PR cursors, assessments,
action history and the model replay cache, so the audit trail of every verdict lives in the graph.

## Benchmark: what does structure buy?

![Grouped bar chart of test split macro F1 for graph reasoning, keyword search and vector RAG](docs/media/benchmark-f1.png)

On the 15 test questions about change impact, graph reasoning scores **F1 1.00**; the best
vector RAG setting scores **0.46** (k=3) and the best keyword setting **0.27** (k=5). Across all
30 test questions: graph **0.79**, vector **0.30**, keyword **0.25**. Keyword and vector use
exactly the same 44 ADR passages, and the vector index is a real FalkorDB cosine index.

This is a synthetic company and questions we wrote, so it measures what the authored structure
buys, not general question answering. Gold labels were written before running the systems; human
review of the labels is still pending. Every k, the latency and the limits are in
[docs/BENCHMARK.md](docs/BENCHMARK.md); the chart is rebuilt by [scripts/plot_benchmark.py](scripts/plot_benchmark.py)
from [bench/results/latest.json](bench/results/latest.json).

## Red team

[35 attacks](docs/REDTEAM.md), all ending in the expected safe outcome on a real FalkorDB:
prompt injection in YAML and PR text, link and mention injection in comments, path traversal,
malformed, huge, deep and "bomb" YAML, forged attestations, write attempts through MCP, false
Analyst answers, unknown entities, fork PRs, stale state and GitHub outages. GitHub writes use an
HTTP mock transport in this suite. It is a regression set, not a security certification.

## Agents and MCP

`premise mcp` starts an official MCP stdio server with 11 read tools: `check_change`,
`check_files`, `resolve`, `decision_lineage`, `guarantee_health`, `who_knows`, `search_evidence`,
`orphaned_decisions`, `load_bearing_guarantees`, `impact_if_broken` and `recall`.

`check_change` and `check_files` ask the same deterministic evaluator before an edit exists.
No hypothetical check creates an assessment, changes graph state, calls a model or posts to GitHub.
Unknown facts require review; missing knowledge is never permission to apply a change.
The Kestrel repository ships an `AGENTS.md` and `CLAUDE.md` that tell agents to check proposed
config files before editing.

```bash
# from the Kestrel checkout; use the absolute path of your Premise virtual environment
claude mcp add premise -- /path/to/Premise/.venv/bin/python -m premise.cli --host 127.0.0.1 --port 6379 --graph premise_kestrel mcp
codex mcp add premise -- /path/to/Premise/.venv/bin/python -m premise.cli --host 127.0.0.1 --port 6379 --graph premise_kestrel mcp
```

The automated test opens a real MCP SDK stdio session against the server. Tool selection by
Claude Code itself is a manual check, not part of the test suite.

The same check from the command line (exit code 2 BLOCKED, 1 NEEDS_REVIEW or ERROR, 0 CLEAR):

```bash
premise check --set paylane.retry_window_hours=72 --json
premise check --file config/partners/paylane.yaml --repo sandbox/kestrel-platform
```

HTTP `POST /api/check` accepts `{changes:[...]}` or `{files:{...}}`. The `/what-if` page is the
same preflight in the browser; nothing is saved or posted.

### Bounded fix agent and Analyst

Deterministic repair always runs, with a 16 evaluation budget. It keeps rejected candidates,
handles independent violation clusters, and verifies their combined remedy as a whole. Only finite
numeric controllable facts may change, at most three per fix. Partial repairs never become fix PRs.

An optional model provider can propose fixes and answer questions, with at most eight fix tool
calls or six Analyst tool calls. A model fix is accepted only when the identical change set was
tested on the graph in that session. Analyst IDs must exist in tool results and citations come
from server rows. The optional [local Codex CLI provider](docs/LOCAL_CODEX.md) uses your signed-in
CLI with its own tools disabled. The Anthropic adapter is implemented, but no successful live
Anthropic API call is claimed. With no provider, everything runs in deterministic mode.

### Knowledge steward

`premise steward` plans maintenance issues for unverified manual assumptions and accepted
decisions with nobody accountable. It defaults to a dry run; `--execute` writes at most ten
marked GitHub issues per sweep and never reopens human-closed issues. `STEWARD_ENABLED=false` by default.

## Architecture

```mermaid
flowchart TB
  GH[GitHub sandbox] -->|15-second poll and git fetch| P[Serialized poller]
  P --> I[Deterministic ingest and revision sweep]
  P --> E[PR overlay and evaluator]
  I --> DB[(FalkorDB: only datastore)]
  E <-->|Typed Cypher queries| DB
  E --> F[Bounded fix agent]
  F -->|Test complete remedy| E
  E --> X[Stale guard and action executor]
  X -->|Status, updatable comment, stacked fix PR| GH
  DB --> T[Shared read tools]
  T --> UI[FastAPI web app and Explorer]
  T --> MCP[Official MCP stdio server]
  T --> QA[Bounded Analyst with verified IDs and citations]
```

The poller performs one assessment at a time; run one app process and one executor. If the
graph is unavailable or ingesting, the assessment is ERROR, the commit status is `error`, and no
comment or fix PR is permitted. Every action rechecks the PR SHA and graph revision before writing.

## v2: a brain that keeps itself current

`premise_v2/` reads Slack, Jira, GitHub and wiki style sources (fixtures, shaped like each API's
responses), finds claims such as "Paylane now retries webhooks for 72 hours", checks in code that
every quote really appears in its source, counts independent origins, and proposes a model update
as a pull request that Premise then checks like any other change. v2 never writes the decision
graph and never decides a verdict; a human merge does.

```bash
premise-v2 run          # dry run; proposals land in .runtime/v2/proposals/
premise-v2 eval --gold
premise-v2 serve        # local evidence review page
```

On a frozen 40 snippet holdout, the extractors reach precision and recall of 1.00 with zero
grounded injection outputs; annotated field accuracy is 0.75 for E3 and 0.857 for E1. These are
small synthetic samples awaiting hand review, not production accuracy. Model outputs from the
local Codex CLI are recorded and replayed offline. Details: [docs/V2.md](docs/V2.md),
[docs/V2_EVAL.md](docs/V2_EVAL.md).

## Run locally

Install Docker Desktop with a running Linux engine. No GitHub or model key is needed to
explore the company and the local scenarios:

```bash
docker compose up --build -d
docker compose exec app premise demo
docker compose exec app premise scenarios
docker compose exec app premise health
docker compose exec app premise ask "Why ADR-012, and who owns it now?"
docker compose exec app python -m pytest -q
```

Open **http://localhost:8000** for Premise and **http://localhost:3000** for the FalkorDB Browser.
The FalkorDB image is pinned to **v4.18.3**. Compose keeps graph data in a named volume with
append-only persistence and exposes ports on loopback only. The app runs as a non-root user on
Python 3.12. To reset the demo, use `premise reset --demo` rather than deleting the volume.

For a host development environment:

```bash
python -m venv .venv
python -m pip --python .venv install -r requirements.lock
python -m pip --python .venv install --no-deps -e .
docker compose up -d falkordb
.venv/bin/premise ingest     # Windows: .\.venv\Scripts\premise.exe
.venv/bin/premise demo
.venv/bin/premise serve
```

Tests use a running server at `FALKORDB_PORT` (default 6379); each test uses an isolated graph
and deletes it afterwards. Linux can install `.[lite]` to use a local FalkorDB module instead of Docker.

### Connect a real GitHub repository

See [docs/PUBLISH.md](docs/PUBLISH.md) for the sandbox repository, token permissions, branch
protection and the red to green rehearsal.

```bash
premise assess --pr 1 --json      # assess and save, no GitHub writes
premise assess --pr 1 --execute   # post the real status and comment; fix PR only if AUTO_FIX_PR=true
premise poll-once                 # ingest main, assess changed open PRs, execute
premise serve                     # starts the poller only when enabled and a token is present
```

The intake fetches `refs/pull/N/head`, checks the expected SHA, and diffs against the PR's own
merge base, so unrelated changes on main are never attributed to the PR. Malformed YAML produces
`R_UNPARSEABLE` and requires review. The fix branch is one atomic commit that preserves comments
and formatting, and its base is the original PR branch.

## Environment variables

Copy `.env.example` to `.env`; never commit tokens. Credentials are excluded from settings repr,
images, remote URLs, graph records and logs.

| Variable | Default / purpose |
| --- | --- |
| FALKORDB_HOST / FALKORDB_PORT | localhost / 6379; compose overrides host to falkordb |
| GRAPH_NAME | premise_kestrel |
| SANDBOX_DIR | sandbox/kestrel-platform, local fixture |
| SANDBOX_REPO | Razeefshaik/kestrel-platform |
| SANDBOX_CLONE_DIR | .runtime/kestrel, dedicated managed clone |
| GITHUB_TOKEN (or GH_TOKEN) | Sandbox-scoped token for actions |
| POLL_ENABLED | Compose defaults false; set true for real polling |
| POLL_SECONDS | 15 |
| AUTO_FIX_PR | false; explicitly enable verified fix PRs |
| STEWARD_ENABLED | false; opt in to maintenance issue writes after a new main graph revision |
| PUBLIC_BASE_URL | http://localhost:8000; use a reachable deployment URL for links in PR comments |
| LLM_PROVIDER | anthropic (default), codex-cli or none; no working provider means deterministic mode |
| ANTHROPIC_API_KEY | Optional |
| LLM_MODEL | claude-sonnet-5-5, configurable through the adapter |
| SINCE_DAYS | 180-day expertise evidence horizon |

## Tests and scenarios

`python -m pytest -q` (348 tests) and `premise scenarios` run against a real FalkorDB server, in
CI on every push. GitHub tests use HTTP-level `httpx.MockTransport`, not fake graph reasoning;
the model is scripted in tests; the MCP test opens a real SDK stdio session.
[docs/VALIDATION.md](docs/VALIDATION.md) records actual results.

| Scenario | Expected and verified verdict |
| --- | --- |
| S1 partner retry 72 h | BLOCKED |
| S1_FIXED TTL and Redis max 72 h | CLEAR_WITHIN_SCOPE |
| S2 email attempts 8 | CLEAR_WITHIN_SCOPE |
| S3 deleted TTL | NEEDS_REVIEW |
| S4 invalid TTL type | NEEDS_REVIEW |
| S5 charge timeout 1500 ms | BLOCKED |
| S6 ad cache 600 seconds | NEEDS_REVIEW |
| S7 ADR model edit | NEEDS_REVIEW |
| S8 README-only change | CLEAR_WITHIN_SCOPE |
| S10 orphan cart assumption | NEEDS_REVIEW |
| S11 two independent violation clusters | BLOCKED; combined remedy independently verified |
| S12 expired currency attestation | NEEDS_REVIEW |

## Scope and limitations

This is a single-process, single-company prototype. Predicates support numeric ordering and
same-type string equality; there is no OR and no weighted risk score. Changes to the decision
model take effect only after review and merge. Polling replaces webhooks. The local web app has no
authentication and binds to loopback; a public deployment needs an access-control boundary, which
is why the public site is a read-only replay. The benchmark and the v2 evaluation are synthetic
and await human label review.

## Hackathon notes

* **Tracks:** Track 1, Agents That Act on Connected Data (the PR agent, verified fix PRs, MCP
  preflight for coding agents) and Track 3, Company Brain (decisions, guarantees, people and
  sources in one graph that answers what holds, who knows and what breaks).
* **Timeline:** the repository history begins on 16 October 2026 (IST), inside the event window.
* **Data:** Kestrel, its people, partners, tickets, chats and runbooks are fictional and synthetic.

## AI use disclosure

Premise was built with AI coding assistants, as the hackathon rules allow:

* **Claude** (Anthropic) and **OpenAI Codex** were used throughout development to move fast:
  drafting and refining designs, writing and reviewing code, tests and documentation, and
  generating the synthetic Kestrel company data.
* **Claude Code** was used for frontend polish and for preparing this README.
* **Codex CLI** can optionally run as the local model provider for proposals and answers.

Changes were reviewed and tested against a real FalkorDB before being kept.

Inside the product, models never decide a verdict, write the decision graph, execute Cypher
from text, or authorize a GitHub action. Verdicts are deterministic Python over parameterized
Cypher, and every model proposal is verified on the graph before it is used.

## Attribution

Kestrel's service naming and selected call edges follow Google's
[Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) (Apache-2.0), with
fictional webhookingress and refundworker services added. No Online Boutique code is redistributed.
The landing page brain model is [3DPX-003765 by Nevit Dilmen](https://commons.wikimedia.org/wiki/File:3DPX-003765_3DModel_of_Brain_Nevit_Dilmen.stl)
([CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)); icons are [Lucide](https://lucide.dev).
