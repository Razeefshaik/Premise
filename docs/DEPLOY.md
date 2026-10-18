# Public live deployment: preflight only

**Not ready to deploy.** This report records inspection on 18 October 2026. Work began at
15:57 IST against the requested 16:00 IST cutoff. No public-mode implementation, credentials,
cloud smoke test or deployment was completed. Use the existing replay and local setup for
this submission. The README has not gained a live-app link.

## Current entry points and route audit

These are current behaviors, not implemented public-mode guarantees. Routes grouped below
share the stated behavior. Framework documentation routes are included.

| Method and route | Current behavior | Public deployment requirement |
| --- | --- | --- |
| GET `/` | Reads health, orphaned decisions, recent assessments and fixture presets; renders landing | Keep; banner |
| GET `/healthz` | Reads graph readiness and revision | Keep |
| GET `/what-if`, `/explore` | Checks readiness and renders UI | Keep; banner |
| POST `/api/check` | Overlay evaluation; repair search enabled by default through `include_fixes` | Keep overlay checks; disable repair search server-side; cap streamed body bytes and rate-limit |
| POST `/api/ask` | Deterministic tools or optional model adapter, depending on configuration | Force deterministic tools; no model or model-cache writes; cap body and rate-limit |
| GET `/api/health` | Reads computed guarantee health | Keep |
| GET `/benchmark`, `/continuity` | Renders page templates | Keep; banner |
| GET `/api/benchmark/questions` | Reads benchmark dataset files | Keep; no benchmark execution |
| GET `/api/benchmark` | Reads recorded JSON results | Keep |
| GET `/assessments/{aid}`, `/api/assessments/{aid}` | Reads existing assessments, evidence and related graph data | Keep; missing records still 404 |
| GET `/entities/{id}` | Resolves entity and reads lineage, health, ownership, history and provenance | Keep; banner |
| GET `/api/graph/timeline` | Reads dated attestation/health information | Keep |
| GET `/api/graph/overview`, `/api/graph/neighborhood` | Reads graph views, including evaluation-date overlays | Keep existing bounds |
| GET `/api/graph/facts` | Reads registered facts/presets | Keep |
| GET `/api/graph/path`, `/api/graph/node/{id}` | Reads paths and node evidence | Keep existing bounds |
| GET `/api/continuity` | Reads main graph, but creates/writes/deletes a temporary graph for betweenness/WCC | Must retain main-graph immutability; decide how to support projections within cloud permissions and resource limits |
| `/static/*` | Serves packaged frontend assets | Keep |
| GET `/docs`, `/redoc`, `/openapi.json` (framework defaults) | API schema/documentation | Account for banner requirement on documentation HTML or explicitly disable documentation UIs |
| v2 GET `/`, `/item/{key:path}`, `/relations`, `/static/*` | Separate v2 server; reads staging/knowledge with visibility handling | Not mounted by v1 bootstrap; do not expose this separate server |
| v2 POST `/item/{key:path}/dismiss` | Writes rejection state to staging | Must return 403 in public mode if v2 server is started |

No direct v1 HTTP endpoint for ingest, steward, GitHub publication or CLI invocation was
found. However, the web application's lifespan starts the poller when polling and a token
are enabled. That background pipeline fetches and ingests main, stores assessments, invokes
optional fix augmentation, publishes statuses/comments/fix PRs, and can run the steward.
Public mode must prevent the entire lifecycle path regardless of supplied flags.

The current What if Apply fix button fills hypothetical values and calls the overlay API;
it does not itself open a GitHub PR. Disabling repair search means the UI must handle absent
fix suggestions honestly. Pre-recorded story behavior also needs checking.

CLI entry points are not shell-executed by web handlers. `serve` shares `create_app`;
`poll-once`, `assess --execute`, `steward --execute`, `ingest`, `reset`, `demo`, benchmark
execution and v2 commands are separate administrative surfaces. A public-mode implementation
must inventory and guard them deliberately rather than assume disabling polling guards all writes.

## Connections that need authenticated/TLS configuration

- `premise/graph/client.py`: underlying FalkorDB constructor currently passes host/port and timeouts only.
- Main entry points: `premise/bootstrap.py`, `premise/web/app.py`, `premise/cli.py`, `premise/mcp_server.py`.
- Secondary clients: `premise/web/continuity.py` and `premise/benchmark/run.py` currently copy only host/port, losing any future auth/TLS unless explicitly propagated.
- v2: `premise_v2/cli.py` constructs Redis and staging/decision/knowledge graph clients; `evaluate.py` and `gold.py` construct isolated evaluation graphs.

Implement optional username/password/TLS without changing current local defaults; hide the
password from repr and logs. Test secondary-client propagation and TLS certificate validation.

## Startup findings

`python -m premise.bootstrap` currently uses the bundled `sandbox/kestrel-platform`; it
does not clone a repository. With polling disabled, it ingests when the graph is not ready,
and skips ingest when ready. This behavior was inspected in source, not cloud-tested.
Repeated/concurrent startup and a changed bundled fixture version still need verification.
It currently binds `0.0.0.0:8000` and does not read `PORT`.

Initial ingest does not create the saved scenario assessments produced by `premise demo`.
A fresh cloud database therefore needs an explicit startup seeding decision if existing
assessment pages and landing history must contain demo records. Never seed from an HTTP request.

## Proposed configuration names (not implemented yet)

`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `FALKORDB_TLS`,
`GRAPH_NAME`, `SANDBOX_DIR`, `PUBLIC_DEMO`, `PORT`, `PUBLIC_BASE_URL`,
`POLL_ENABLED`, `AUTO_FIX_PR`, `STEWARD_ENABLED`, `LLM_PROVIDER`.

Public mode must override unsafe flags and provider settings, enforce the requested 403
message, and add the public-demo banner. Validate the body limit before JSON parsing, including
chunked requests. Rate limiting needs bounded memory and a trusted-proxy/IP policy so forwarded
headers cannot bypass it. Consider expensive continuity/graph endpoints as well as Ask and What if.

Do not supply GitHub or model tokens to the public host. Enter database credentials only
through host secrets or the approved local shell, never source files or chat.

## Hosting findings and future setup

The user has not selected a host. On 18 October 2026, the official
[Hugging Face Spaces overview](https://huggingface.co/docs/hub/spaces-overview) says creating
a Docker Space requires a paid plan, despite CPU Basic having no hourly cost. Its documented
outbound ports also require checking against the actual cloud database endpoint.

[Render's free service documentation](https://render.com/docs/free) supports free web
services and describes operation without a payment method. Account-specific signup/card
verification was not tested. Free services sleep after 15 minutes and can be suspended for
unusually high outbound traffic, including external database access.

If deployment is resumed after the submission with a new time budget:

1. Finish public-mode code and the required regression, immutability and rate-limit tests first.
2. Provision FalkorDB Cloud; privately record its endpoint, port, username, password and TLS requirement.
3. Choose a host that accepts the account without a card and permits outbound database TCP/TLS.
4. For Render, create a Web Service using the repository Dockerfile and choose Free. Do not deploy today's unguarded main. Use only the reviewed, tested deployment commit after the user pushes it.
5. Enter the configuration in host settings. Start with `python -m premise.bootstrap`; the pending code must read the host's `PORT` and force public mode's safe settings.
6. Confirm `/healthz`, all retained pages, blocked write routes, deterministic Ask, and the Paylane overlay from outside the local machine. Compare main node/edge counts and fact hashes before/after batches.
7. Only after the user confirms success, add the live URL to the README. Keep the replay available.

## Validation and diff for this timebox

- Source inspection only: routes, entry points, connection constructors, startup, Apply fix behavior.
- Full pytest suite: **not run**. Scenarios: **not run**. Cloud credentials: **not supplied**.
- Cloud and public endpoint smoke tests: **not run**. Immutability tests: **not implemented/run**.
- No runtime code, verdict logic, verdict Cypher, Dockerfile or README changes.
- Only this deployment preflight report was added on `deploy/live`; no push or deployment.

This is a handoff, not evidence that the requested public deployment is safe or complete.
