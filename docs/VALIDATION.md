# Validation record

Run date: October 16, 2026 (IST). Initial build checks and subsequent live checks are distinguished below.

## F1 preflight feature merge gate

`feat/check-change`: **143 tests passed** (47.42 s), **12/12 CLI scenarios passed**,
and the desktop/mobile browser script passed against an isolated graph on port 8002.
The official MCP stdio test lists 11 tools and executes a real S1 `check_change`.
Read-only tests compare node counts, edge counts and GraphState properties and forbid
write keywords on the graph read path. CLI exit codes, malformed YAML, unknown facts,
argument limits, traversal rejection and HTTP validation were exercised.
Evidence: ignored `artifacts/f1/validation.json`, logs and browser screenshots.
Kestrel's separate publishing checkout has local commit `1c045f8` for its agent instructions;
no repository was pushed. Claude Code is not installed, so its interactive automatic
tool-selection demonstration was not executed.

## Optional local Codex branch

Branch `feat/local-codex-cli` starts from `main` commit `8bf6202`. The native CLI provider
is opt-in; the default Anthropic provider and its request rules are preserved.

| Check | Actual result |
| --- | --- |
| Full Windows host suite | **117 passed**, 50.30 s |
| Standalone Python 3.12 image, real FalkorDB | **117 passed**, 23.05 s; no host source mount or login required |
| Deterministic CLI scenarios, separate graph | **12/12 passed** |
| Native CLI used for live calls | **codex-cli 0.162.0-alpha.17.2**, resolved from the installed executable on PATH |
| Live `/api/ask` health question | **llm / codex-cli**, load-bearing and guarantee-health tools, cited sources; 28.67 s |
| Live `/api/ask` decision question | **llm / codex-cli**, resolution, lineage and evidence search, cited sources; 36.34 s |
| Live `/api/ask` expertise question | **llm / codex-cli**, resolution and ownership evidence, cited sources; 28.39 s |
| Live S1 fix controller | Called `violation_context`, then `test_fix`; TTL 72 plus Redis max 72 returned **all_hold=true** and was accepted as **verified / llm** |
| Full live rehearsal | **success=true**, 121.28 s; fresh isolated graph, no replayed model steps or GitHub writes |
| Windows launcher / actual browser | Host app on port 8001 with a separate graph; accepted answer displayed **provider: codex-cli**. Desktop 1440x1050 and mobile 390x844 passed, no page errors or overflow, Mermaid rendered |

The live repair prompt excluded the existing deterministic fix candidates. The controller
accepted only the identical changes map actually tested in that session. Raw tool rows and
provider usage events were real; no model identity beyond the requested CLI default is claimed.
Exact-request replay remains distinct from provider-side cached input tokens.

The first rehearsal correctly fell back when prose did not pass the conservative verifier.
Inspection found a false rejection of a guarantee *depending on an unverified assumption*.
The verifier now checks that assumption state against the assumption, while still rejecting
an explicit claim that a holding guarantee is unverified. Three regression cases cover the
distinction; health wording is also constrained in the prompt. The final full rehearsal above
passed with all three answers accepted, rather than counting fallback as model success.

Evidence files are ignored artifacts: `codex-rehearsal.json`,
`codex-rehearsal-before-health-fix.json`, `codex-diagnose.json`, `codex-ui-check.json`,
and `codex-*.png`. Tests for process timeout/output bounds, secret-free child environments,
tool allowlists/budgets, exact replay, rejected outputs and provider fallback need no Codex login.
The local CLI is not bundled into Docker. Live Anthropic compatibility, interactive external
MCP client setup and a Codex-backed remote GitHub PR write were not tested by this rehearsal.
See [LOCAL_CODEX.md](LOCAL_CODEX.md) to run the branch locally.

## Leader review follow-up

- The five supplied probes reproduced all five original behaviours before fixes: **5 passed**, 4.95 s.
- Final host suite: **96 passed**, 69.59 s, against real FalkorDB 4.18.3.
- Final standalone Python 3.12 image suite: **96 passed**, 18.42 s, without a host source mount or `.env`.
- Fresh-graph container startup and desktop/mobile browser rehearsal passed on a temporary local port
  with polling disabled and no GitHub/provider credentials. Mermaid rendered; no page errors or
  document overflow. Attestation names/dates and the derived lexical comparison were inspected.
- Standalone scenario CLI in an isolated graph: **12/12 passed**; 275 nodes and 488 authored edges ingested.
- Regressions cover merge-base selection, YAML review reasons and source locations, persistent error
  backoff, main-sync outage backoff, exception tracebacks, grounding limits, Markdown escaping,
  controller/executor revert guards and the URL ban. Web tests cover derived lexical terms and readable attestations.
- The fresh-start rehearsal caught an empty-key `RO_QUERY` error after narrowing exception handling.
  That specific server response is now treated as an uninitialized graph; other query errors still surface.
  The additional bootstrap regression accounts for test 96. Earlier intermediate runs passed 95 tests
  on the host (44.30 s) and Python 3.12 image (19.42 s).
- Anthropic live calls remain untested: no provider key is configured. Token rotation remains a user action.
- The existing app on port 8000 was not recreated with the exposed token. Replace the token and
  run `docker compose up --build -d` to activate the final changes in that long-running app.

Detailed finding dispositions are in [REVIEW_FIXES.md](REVIEW_FIXES.md).

## Live follow-up: repeated assessment status repair

The live PR #3 assessment correctly returned CLEAR_WITHIN_SCOPE, but GitHub remained
pending. Status history showed success followed by pending on the same SHA/context.
The executor had deduplicated the final success using its saved Action record, even
though the new assessment had posted pending. Final statuses now always pass the stale
guard and are re-posted; comments and fix PRs retain their deduplication rules.

- A new regression reproduced the stuck-pending bug before the fix.
- After the fix, all **14 GitHub regression tests passed** in 21.13 seconds.
- A real reassessment of [PR #3](https://github.com/Razeefshaik/kestrel-platform/pull/3)
  posted success, confirmed through GitHub's combined-status API.
- The same live read confirmed success for [PR #1](https://github.com/Razeefshaik/kestrel-platform/pull/1).
- GitHub confirmed [fix PR #2](https://github.com/Razeefshaik/kestrel-platform/pull/2)
  was merged by the user into `scenario/s1-retry-72`.

The initial build record below predates those user-run live rehearsals.

| Check | Actual result |
| --- | --- |
| Original milestone regressions | **47 passed**, 89.53 s, real FalkorDB 4.18.3 |
| GitHub / agent / Brain / MCP tests | **21 passed**, 104.36 s |
| Full host suite with expanded corpus and source permalink regression | **70 passed**, 188.36 s |
| Python 3.12 container suite against real FalkorDB | **70 passed**, 219.81 s |
| Final standalone image, no source mount or `.env` | **70 passed**, 75.58 s; built from clean runtime commit `3f88f3f` |
| Headless Chrome UI | Desktop 1440×1050 and mobile 390×844 passed; no page errors or document overflow; Mermaid SVG rendered |
| Final corpus | **20 distinct tickets, 40 chat messages, four runbooks** |
| Clean local clone → standalone Docker startup | `/healthz` HTTP **200**, ready revision 1; no `.env` or GitHub token in image |
| Scenario CLI | **12/12 passed** |
| FalkorDB module | `MODULE LIST` and startup logs confirm **4.18.3** |
| GitHub account and both repositories | Authenticated GET requests succeeded; account `Razeefshaik`, both repo lookups HTTP 200 |
| Remote writes / pushes during initial build | **None**; subsequent real rehearsal is documented above; the user pushes manually |
| Anthropic live calls | **Not run**; no provider key configured |
| Video / hackathon submission | **Not recorded or submitted** |

The host suite ran on Python 3.13. The Docker deployment uses the required Python 3.12.
Both test environments emit one dependency deprecation warning: Starlette's test client warns
about httpx compatibility. Tests still pass. The requirements lock records the versions
actually installed; it contains no credentials or local editable paths.

What the integration tests execute:

- Real FalkorDB ingestion, complete-prerequisite assessment and immutable main facts.
- HTTP-level GitHub status/comment/fix calls through `httpx.MockTransport`.
- Multi-file fix in one Git tree/commit, stacked base, and preservation of original facts.
- Duplicate execution, marker-based comment update, crash reconciliation and revised comments.
- Changed PR heads, changed graph revisions, closed PRs, graph not ready and graph unreachable.
- External, partial and unverified fixes blocked by the executor/controller.
- Actual local Git repositories proving PR merge-base diff isolation and stale-fetch rejection.
- Conditional HTTP polling, rate-limit errors and new-main reassessment.
- Scripted provider failures, untested/false fix rejection, append-only thinking blocks,
  and absence of prohibited request parameters.
- Current health, expired manual attestation, decision lineage, PageRank and reviewer evidence.
- Analyst rejection of ADR-099, unknown topics, citation verification, and HTTP UI routes.
- An official MCP client starts the real stdio server, lists nine read tools, and calls health.
- Re-ingestion clears authored properties removed from source, including attestation expiry.

Each graph test uses an isolated `premise_test_<uuid>` graph and cleans it afterward.
No mocked graph substitutes for FalkorDB. Host artifacts, including JUnit XML and browser
screenshots, live under ignored `artifacts/` so generated output is not mixed with source.

The final standalone image was built from a clean local Git clone, without the host `.venv`
or ignored files. Its bootstrap ingested the bundled company into a new graph, and its
health endpoint returned ready. Runtime source changes after the full container suite
received focused regression checks: proposed-value commit citations (1 passed, 7.28 s)
and Analyst argument/unknown-lookup evidence rejection (1 passed, 38.73 s).

One initial regression run was invalidated by a container recreation (three connection
errors); it was repeated on a stable server. The successful 47-test and 70-test runs above
supersede that interrupted run. No passing claim is made from the interrupted execution.

Still required after manual publication:

1. Revoke and replace the token exposed in the shared workspace ZIP; push the local fixes.
2. Required `premise/decisions` status configured on sandbox `main`, if the token/account
   has administration access.
3. Live model/API compatibility with the configured model and key; deterministic mode
   already works independently.
4. Claude Desktop or MCP Inspector interactive rehearsal; the SDK protocol test is automated.
5. A three-minute video, public playback check, public repo visibility and final entry form.

Follow [PUBLISH.md](PUBLISH.md) and [DEMO.md](DEMO.md) for those steps. They intentionally
remain manual instead of claiming remote work that was postponed by the user.
