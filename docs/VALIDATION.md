# Validation record

Run date: October 16, 2026 (IST). No results below imply a live GitHub demonstration.

| Check | Actual result |
| --- | --- |
| Original milestone regressions | **47 passed**, 89.53 s, real FalkorDB 4.18.3 |
| GitHub / agent / Brain / MCP tests | **21 passed**, 104.36 s |
| Full host suite with expanded corpus and source permalink regression | **70 passed**, 188.36 s |
| Python 3.12 container suite against real FalkorDB | **70 passed**, 219.81 s |
| Headless Chrome UI | Desktop 1440×1050 and mobile 390×844 passed; no page errors or document overflow; Mermaid SVG rendered |
| Final corpus | **20 distinct tickets, 40 chat messages, four runbooks** |
| Scenario CLI | **12/12 passed** |
| FalkorDB module | `MODULE LIST` and startup logs confirm **4.18.3** |
| GitHub account and both repositories | Authenticated GET requests succeeded; account `Razeefshaik`, both repo lookups HTTP 200 |
| Remote writes / pushes | **None**, per user's instruction to push manually |
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

One initial regression run was invalidated by a container recreation (three connection
errors); it was repeated on a stable server. The successful 47-test and 69-test runs above
supersede that interrupted run. No passing claim is made from the interrupted execution.

Still required after manual publication:

1. S1 real PR failure, exact comment evidence, one real stacked fix PR, manual merge and
   original PR success; S2 real PR success (T20).
2. Required `premise/decisions` status configured on sandbox `main`, if the token/account
   has administration access.
3. Live model/API compatibility with the configured model and key; deterministic mode
   already works independently.
4. Claude Desktop or MCP Inspector interactive rehearsal; the SDK protocol test is automated.
5. A three-minute video, public playback check, public repo visibility and final entry form.

Follow [PUBLISH.md](PUBLISH.md) and [DEMO.md](DEMO.md) for those steps. They intentionally
remain manual instead of claiming remote work that was postponed by the user.
