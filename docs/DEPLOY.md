# Public live deployment

Work is on `deploy/live`. Changes are local until reviewed; no deployment branch has been
pushed. The earlier 16:00 IST cutoff was withdrawn: the user gave eight more hours.
The README live-app link stays unchanged until a real deployment is confirmed.

## Free hosting and account setup

Use **Render Web Service (Docker, Free)** for the app and **FalkorDB Cloud** for its graph.
These are separate services: Render serves the website, and FalkorDB stores the company graph.

Checked against official documentation on 18 October 2026:

- [Render Free](https://render.com/docs/free) offers web services with 750 instance hours
  per workspace/month. Apps sleep after 15 idle minutes and can take about a minute to wake.
  No-card accounts are documented, but account-specific verification has not been tested.
  Excess outbound traffic, including external database traffic, can cause suspension.
- [FalkorDB plans](https://www.falkordb.com/plans/) advertises a Free plan, but currently
  lists TLS as excluded. Check the actual instance connection screen. Website HTTPS does
  not encrypt the separate Render-to-database connection. Do not claim transport security
  if that endpoint only supports plaintext. The user confirmed that their Free instance has
  no TLS and explicitly chose this tradeoff for an isolated fictional-data demo. Use a
  unique password, no private company data, and keep TLS disabled for this endpoint.
- [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview) currently requires
  a paid plan to create a Docker Space, despite CPU Basic having no hourly charge.

### Do now: accounts only

1. Sign up at [FalkorDB Cloud](https://app.falkordb.cloud/).
2. Create a dedicated Free demo instance, if the account offers it. Use only the fictional
   sandbox data. Record its connection settings privately; never paste credentials into chat.
3. Check the offered port and TLS support. Do not infer them from examples or assume port 6379.
4. Sign up at [Render](https://dashboard.render.com/) using GitHub. Connect only the Premise
   repository if the permission picker permits that scope.
5. Confirm that the Free web-service plan is available without purchasing anything. Stop
   before deploying the old main branch: it does not contain these public-mode protections.

### After local review and the user's push

1. In Render, choose **New -> Web Service**, then the Premise repository.
2. Select the reviewed branch/commit containing these changes. Choose **Docker**, the
   repository root as build context, and `./Dockerfile`. Select **Free** compute.
3. Use the region nearest the database when both providers offer that region.
4. Enter the environment settings below in Render's Environment settings. Enable public
   demo mode and use a dedicated graph namespace. Do not upload `.env` or add GitHub/model keys.
5. Leave the Docker command at its default: `python -m premise.bootstrap`. Render supplies
   `PORT`; the process binds to it on `0.0.0.0`. Its local fallback port is 8000.
6. Set the health-check path to `/healthz`. Use one instance/worker; request limits are
   process-local. Turn off automatic deploys during review if offered.
7. Create the service after the exact commit and environment have been reviewed. Watch logs
   until graph startup is complete and the health check is successful.
8. Copy the generated HTTPS address into `PUBLIC_BASE_URL` in the host's settings.
9. Run the smoke checks below against that HTTPS address. Test the link while logged out,
   including after an idle cold start. Confirm success before adding it to the README.

## Environment variable names

No credentials or concrete connection values belong in this document.

| Variable | Purpose |
| --- | --- |
| `PUBLIC_DEMO` | Enable the public safety boundary; required for this deployment |
| `FALKORDB_HOST` | Cloud endpoint hostname, without a URL scheme |
| `FALKORDB_PORT` | Exact database port from the connection screen |
| `FALKORDB_USERNAME` | Optional database username |
| `FALKORDB_PASSWORD` | Database password; enter as a host secret |
| `FALKORDB_TLS` | Enable only when the endpoint supports TLS; verifies certificate and hostname |
| `GRAPH_NAME` | Dedicated public demo graph, separate from existing company/v2 graphs |
| `SANDBOX_DIR` | Optional override for the bundled fixture directory |
| `PORT` | Host-supplied HTTP listening port |
| `PUBLIC_BASE_URL` | The service's public HTTPS origin |
| `POLL_ENABLED` | Forced off by public mode regardless of supplied setting |
| `AUTO_FIX_PR` | Forced off by public mode |
| `STEWARD_ENABLED` | Forced off by public mode |
| `LLM_PROVIDER` | Forced to the disabled provider by public mode |

No GitHub token, Anthropic key or Codex login is needed. Auth/TLS settings propagate to
FalkorDB clients, temporary graphs and the Redis connections in v2 administration.
Defaults preserve unauthenticated local Docker use. Passwords are excluded from Settings repr.

## Startup and request boundaries

The bootstrap uses `sandbox/kestrel-platform` bundled in the image. It neither clones a
repository nor calls GitHub. If the graph is ready, it skips ingestion; otherwise it loads
the fixture. Public startup seeds four labelled fixture assessments without repair search.
Restarting a ready graph skips existing seed assessments for that revision.

Continuity's native betweenness/WCC projections are computed once during app startup in
owned temporary graphs, which are then deleted. Requests use their cached results. The
query viewer marks these traces `recorded_at_startup`; their timings are startup timings.
A changed main-graph revision invalidates the cache and returns 503 until restart. These
algorithms describe continuity and never decide verdicts.

Public HTTP requests cannot call the GraphClient write/delete methods. Unsupported mutation
methods are rejected before route dispatch. Existing What if checks only evaluate overlays;
explicit repair-search requests are denied. Story mode tests the bundled repair preset as
an overlay and labels it as a preset, not a newly generated fix.

Raw bodies are capped at 64 KiB before JSON parsing, including chunked bodies, with a
10-second body-read timeout. Ask and What if share 30 requests per minute per observed
client IP; other API reads and landing reads allow 120. At most four expensive requests
run concurrently. The IP table is bounded to 2,048 buckets; new buckets are rejected when
full. Limits reset on restart and require a single worker.

The server disables proxy-header rewriting and does not trust user-supplied forwarded IPs.
Behind Render, requests may therefore share a proxy's bucket. This deliberately favors a
conservative limit over spoofable per-visitor identity. A verified trusted-proxy policy is
needed before increasing traffic or using multiple workers.

## Keepalive

[Keep live demo awake](../.github/workflows/keepalive.yml) requests the public graph
overview every ten minutes and can also be run manually from GitHub Actions. It needs no
repository checkout, credentials or token permissions. A successful request prints `awake`.
The supplied workflow emits a warning if all requests fail, so a green job alone does not
prove the service responded; check its log for `awake`.

GitHub scheduled jobs are best effort and may be delayed or dropped during high load;
this reduces idle time but is not an uptime guarantee. See
[GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Route audit

| Method and route | Public behavior |
| --- | --- |
| GET `/` | Live graph health, presets, orphaned decisions and stored fixture assessments |
| GET `/healthz` | Graph ready/revision, 200 or 503 |
| GET `/what-if`, `/explore` | Interactive overlays, graph, time machine and query viewer |
| POST `/api/check` | Overlay only, bounded body/rate; omitted repair flag forced off; explicit repair flag returns 403 |
| POST `/api/ask` | Deterministic read tools only; no adapter or model-cache writes |
| GET `/api/health` | Computed guarantee health |
| GET `/benchmark`, `/continuity` | Page views with public banner |
| GET `/api/benchmark/questions`, `/api/benchmark` | Bundled benchmark data/results; never executes benchmark/model download |
| GET `/assessments/{aid}`, `/api/assessments/{aid}` | Stored assessment/evidence; 404 if missing |
| GET `/entities/{id}` | Entity lineage, ownership, health, history and source evidence |
| GET `/api/graph/timeline` | Attestation dates and evaluated health |
| GET `/api/graph/overview`, `/api/graph/neighborhood` | Bounded graph views with optional evaluation date |
| GET `/api/graph/facts` | Registered facts and fixed scenario presets |
| GET `/api/graph/path`, `/api/graph/node/{id}` | Paths and node evidence |
| GET `/api/continuity` | Main graph reads plus startup-recorded native projection results |
| GET `/static/*` | Packaged assets |
| GET `/docs`, `/redoc`, `/openapi.json` | Schema/docs; documentation HTML includes public banner |
| All other mutation requests | 403 before dispatch; no GitHub/ingest/steward action route exists in v1 |
| v2 GET `/`, `/item/{key:path}`, `/relations`, `/static/*` | Separate local review server; not mounted or launched by public bootstrap |
| v2 POST `/item/{key:path}/dismiss` | 403 in public mode, even if someone constructs the separate v2 app |

The exact disabled message is: **Disabled in the public demo. Run Premise locally for the full version.**
Every application HTML page includes the public demo banner. Normal local mode keeps its
existing routes, repair search, optional adapters and polling behavior.

No web handler shells out to a CLI. The `serve` CLI shares this app and its public boundary.
In public mode, main CLI `health`, `ask`, `check` and `serve` remain available (`check` omits
repair search). `ingest`, `reset`, `demo`, `assess`, `assess-scenario`, `scenarios`, `poll-once`,
`reconcile`, `steward`, `bench`, `redteam` and `mcp` are denied. All v2 CLI commands except
`registry-check` are denied. Startup seeding is the deliberate pre-request exception.
Direct pipeline construction, model-adapter construction and bounded fix augmentation are
also denied when given public settings. Core verdict code and verdict Cypher are unchanged.

## Verification

Run the regular full suite against local FalkorDB with public mode disabled:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m premise.cli --graph premise_deploy_validation scenarios
```

Use a separately ingested validation graph for scenarios; never target the live database.
Run a public-mode instance with its credentials supplied privately through environment
variables, then point the smoke script at it:

```powershell
.\.venv\Scripts\python.exe scripts/check_public_demo.py --base-url http://127.0.0.1:8000 --verify-database
```

The operator-side `--verify-database` option reads the configured graph directly and compares
node count, edge count and a SHA-256 hash of all fact values before/after repeated HTTP calls.
It prints no credentials. For external HTTP-only checks, omit that option and supply the
public HTTPS URL. Database immutability is then explicitly reported as not checked.

The smoke script checks kept pages, graph/date/path/continuity/benchmark APIs, stored
assessments, Paylane at 72 (BLOCKED, four broken guarantees), the repair preset (CLEAR),
ADR-012 deterministic Ask with citations, and disabled actions (403).

### Actual results for this branch

- Focused public/config plus existing web/preflight/continuity tests: **62 passed**.
- Public/config tests after adding the request-context write boundary: **24 passed**.
- Full suite: **373 passed in 415.89 seconds (6 minutes 55 seconds)**.
- Twelve scenarios: **12 PASS** against a separate local graph.
- Docker image build: **passed locally** on the final code image.
- Public container API smoke: **PASS** (port supplied as 10000, published locally on 8017).
  Node/edge counts stayed **284 / 510**; the fact hash remained
  `e072844bd6e1b5ea305e7d60400b02c2127dd34ccbe6e6eb80dae200cf541185`.
- Public browser smoke: **PASS** at 1440x900 and 390x844: visible canvas/verdict,
  G_DEDUPE labelled broken, complete preset-repair story, zero page errors.
- User confirmed a FalkorDB Free instance without TLS. The deployed endpoint is `https://premise-43eh.onrender.com/`; cloud HTTP API smoke checks passed. Operator-side cloud credentials were not supplied, so direct cloud graph immutability was not checked.
- The user pushed the deployment branch and deployed it on Render. The README live link is still unchanged pending confirmation of working pages.

## Final local diff for review

- Optional database username/password and verified TLS, propagated to secondary graphs
  and Redis administration clients. Local defaults are preserved.
- Public request boundary, deterministic Ask, overlay-only checks, disabled action paths,
  bounded bodies/rates/concurrency, public banner, and startup-only continuity projections.
- Restart-safe fixture ingestion and labelled example assessments; host-provided HTTP port.
- Public story uses the bundled repair preset, with desktop/mobile canvas space for the banner.
- Regression tests, public API/browser smoke scripts, environment example and this route audit.
- **No changes to verdict evaluation code or verdict Cypher.** No README live link added.

Review the complete patch locally with `git diff main...deploy/live`. The ignored review
copy is `.runtime/deploy-live.diff`; it must not be committed. After review, the user can
publish only this branch with `git push -u origin deploy/live` and select it in Render.
Main does not need to be merged for this deployment.

## HTTPS asset correction after the first Render deployment

The live database APIs returned successful results, but Explorer, Continuity and Benchmark
rendered absolute HTTP asset links from the internal request scheme. Render terminates
HTTPS before forwarding to Uvicorn; browsers blocked those scripts and styles as mixed
content. The HTTP localhost smoke did not expose that hosting difference.

The correction uses root-relative asset paths in those three templates. It does not trust
forwarded client IPs or change the request limits. Six new regression cases simulate an
HTTP upstream behind an HTTPS proxy in public and normal modes.

- Targeted HTTPS/public/Explorer tests after the correction: **31 passed**.
- Replay rendering of all three corrected templates: **PASS**, with relative replay assets.
- Hosted API smoke: **PASS** for retained pages/APIs, Paylane at 72 (BLOCKED, four broken
  guarantees), the repair preset (CLEAR), ADR-012 deterministic Ask with sources, and
  forbidden write requests (403). HTTP status alone does not prove browser scripts loaded.
- Browser diagnosis against the hosted APIs: Explorer loads and shows hypothetical broken
  labels; Benchmark displays the actual recorded graph F1 and chart; Continuity displays
  departure analysis. These checks corrected only asset URLs inside the test browser.
  Benchmark and Continuity then reported no browser errors. This proves the correction
  addresses the observed failure; it does not mean the server already serves the hotfix.
- The 373-test full-suite result above precedes this template correction; it is not a
  claim that the full suite was repeated after the correction.
- The asset correction must be pushed and deployed before the public browser fix is live.
