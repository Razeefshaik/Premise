# Premise main branch: three features for the hackathon

**Audience:** the Codex agent working on `main`, and Razeef reviewing its work.
**Base:** `main` after the fast forward to `383e610` (local Codex provider plus the review fixes). If `main` is still at `fa70771`, merge `origin/feat/local-codex-cli` first.
**Status:** this is the build spec. Each feature is small, read only or opt in, and independently mergeable.

## 0. Rules that apply to all three features

These rules protect the submission. Read them before writing code.

1. **Main stays submittable at every commit.** Build each feature on its own short branch (`feat/check-change`, `feat/what-if`, `feat/steward`). Merge to `main` only when all of these hold:
   - the full test suite passes, at 117 tests or more;
   - `premise scenarios` passes 12 of 12;
   - the browser check script passes.
2. **Order:** F1, then F2 (the what if panel, which reuses F1), then F3 (the steward, which writes to GitHub). F3 is optional. Drop it if F1 and F2 are not merged by Oct 17, 14:00 IST.
3. **Feature freeze: Oct 17, 18:00 IST.** After that, only bug fixes, docs and the video.
4. **The verdict stays deterministic.** None of these features let a model influence a verdict, a guarantee status, or which fixes count as verified. The rule is the same as today: the model proposes, the graph checks.
5. **Never write to the reasoning graph.** F1 and F2 must not create, change or delete any node or edge. F3 writes only its own operational records (`StewardAction` nodes), never domain nodes.
6. **Do not edit these core files:**
   - `premise/reasoning/evaluate.py`
   - `premise/reasoning/repair.py`
   - `premise/reasoning/models.py`
   - `premise/graph/queries/*.cypher`, apart from new query files
   - the existing scenario expectations

   If a feature seems to need a change there, stop and ask.
7. **Escape everything rendered to GitHub or HTML.** Use `premise.agent.render.safe` for markdown; Jinja autoescape already covers HTML.
8. Every new public behavior needs tests that run against the real FalkorDB, using the existing fixtures (`kestrel`, `new_graph`, `repo_copy`).

## F1. `check_change`: Premise as a preflight check for coding agents

### What it is, in one paragraph
Today Premise judges a change after a PR exists. F1 lets any agent (Claude Code, Codex, Cursor) ask Premise *before* editing files: "if I set these values, or write these files, what breaks?" Premise runs the exact same assessment pipeline as a PR, but on an in memory overlay. It stores nothing and posts nothing, and it returns:
- the verdict and the reasons;
- the broken and unknown guarantees, with their chains;
- the affected decisions and who should review them;
- the fixes that the graph has verified.

### Why it matters for judging
Track 1 is "agents that act on connected data". Here an AI agent's action is governed by the company's knowledge graph before the action happens. The demo is 20 seconds:
1. In Claude Code, the user asks for the Paylane retry window to go to 72 hours.
2. The agent calls Premise and gets BLOCKED, with four broken guarantees.
3. The agent proposes the verified fix instead.

### Interfaces
Two read only tools, added to the shared tool registry in `premise/graph/tools.py`. Because MCP, the web app and the Analyst all use that registry, all three get them.

```text
check_change(changes: list[ChangeItem], include_fixes: bool = true) -> CheckResult
  ChangeItem = { fact: str }        # a registered fact id, e.g. "paylane.retry_window_hours"
             | { file: str, key: str }   # or a file path plus a dotted key
             plus exactly one of: value: str|int|float|bool  or  delete: true
  limits: 1 to 20 items; values are JSON scalars only

check_files(files: dict[path, text|null], include_fixes: bool = true) -> CheckResult
  proposed full contents of files the agent is about to write (null means delete)
  limits: 1 to 10 files, at most 200 KB each, POSIX paths relative to the repo, no "..", no absolute paths
```

### Behavior

**`check_change`**
1. Resolve each item to a registered fact.
   - Use `facts_by_id` for fact ids. For file plus key, add a new query `facts_by_file_key.cypher`.
   - Normalize the value with `premise.ingest.parse.normalize_value`, so that `"24h"` stays a string and becomes unevaluable, exactly like scenario S4.
   - Build the `ChangedFact` list with `old` set to the main value.
2. **Unknown facts are never "safe".** Any item that does not resolve to a registered fact produces a `R_UNTRACKED` reason, which means NEEDS_REVIEW, and its detail says: `"<x> is not a tracked fact; Premise has no evidence about its impact"`. This follows the existing principle that missing knowledge means `not_in_graph`, never "no impact".
3. Call `premise.reasoning.assess.assess(client, changes, changed_paths=[...], model_change=False, run_repair=include_fixes, pr=None, head_sha=None)`.
   - Merge `R_UNTRACKED` reasons in exactly as `poller.assess_pr` merges intake issues: drop `R_ALL_HOLD` and `R_NO_TRACKED_FACTS`, and lift the verdict to at least NEEDS_REVIEW.
   - If any item was untracked, clear the fixes.

**`check_files`**
- Call `overlay_from_files(client, files, issues=issues)` with `base_files=None`, meaning compare against main, then follow the same path as above.
- Set `model_change` from `is_model_path`, exactly as intake does.
- Malformed YAML becomes `R_UNPARSEABLE`, as in the poller.

**Both tools**
- Must be strictly read only. `assess` and `Repairer` already only read; do **not** call `Store.save`.
- Respect `GraphTools.guard()`: a graph that is not ready gives an error, never a verdict.

**Compact result (`CheckResult`).** Agents have small context windows, so return only this:

```json
{
  "hypothetical": true,
  "stored": false,
  "graph_rev": 1,
  "verdict": "BLOCKED",
  "reasons": [{"code": "R_BROKEN_T1", "detail": "G_DEDUPE is broken via G_DEDUPE -> A_RETRY_WINDOW"}],
  "changed": [{"fact": "paylane.retry_window_hours", "old": 24, "new": 72, "controlled_by": "external"}],
  "not_holding": [{"id": "G_DEDUPE", "status": "broken", "baseline": "holds", "tier": 1,
                   "chain": ["G_DEDUPE", "A_RETRY_WINDOW"], "promised_by": ["ADR-007"]}],
  "decisions": [{"id": "ADR-012", "reviewers": ["p_jun", "p_anika"], "departed": ["p_lena", "p_marco"]}],
  "verified_fixes": [{"changes": {"webhook.dedupe_ttl_hours": 72, "redis.max_ttl_hours": 72}}],
  "advice": "Do not apply this change alone. Apply a verified fix together with it, or ask the listed reviewers."
}
```

- `advice` is a fixed string chosen by verdict. It is **never** model generated.
- Only `status == "verified"` fixes appear, and the field is empty when `include_fixes` is false.

### Wiring
- **`premise/graph/tools.py`:** add pydantic arg models (`extra="forbid"`, with the limits above) and both methods. Add them to `TOOLS` with clear descriptions such as "Hypothetical: check proposed fact values against every affected guarantee. Stores nothing."
- **`premise/mcp_server.py`:** register both tools.
- **CLI:** add `premise check --set paylane.retry_window_hours=72 [--set ...] [--file path ...] [--json]`. It exits with code 2 for BLOCKED, 1 for NEEDS_REVIEW or ERROR, and 0 for CLEAR, so it also works as a local pre-commit hook.
- **Web:** add `POST /api/check` taking `{changes:[...]}` or `{files:{...}}`. F2 uses it.
- **Agent instructions for the demo:** in the **kestrel-platform** repo (not Premise), add an `AGENTS.md` (read by Codex) and a `CLAUDE.md` (read by Claude Code) with this text:
  > Before editing any file under `config/`, call the `premise` MCP tool `check_files` with the full proposed file contents. If the verdict is BLOCKED, do not write the change; propose the returned verified fix instead and name the reviewers.
- **Docs:** add a "Pre-flight checks for coding agents" section to the README with the two MCP setup commands. One is `claude mcp add premise -- <python> -m premise.cli mcp`; for Codex, use `codex mcp add` or `~/.codex/config.toml`. **Verify the exact Codex syntax on the machine** before documenting it.

### Tests (`tests/test_check_change.py`)
1. Use the S1 values through `check_change`. Expect BLOCKED, `not_holding` IDs equal to {G_DEDUPE, G_CHARGE_ONCE, G_LEDGER_CONSISTENT, G_REFUND_MATCH}, and the verified fix {dedupe 72, redis 72}.
2. Use the S1_FIXED values. Expect CLEAR_WITHIN_SCOPE.
3. Use the S4 string value `"24h"`. Expect NEEDS_REVIEW with R_UNKNOWN.
4. Check an unknown fact `foo.bar=1`. Expect NEEDS_REVIEW, R_UNTRACKED and no fixes. Mix an unknown fact with the S2 values and expect at least NEEDS_REVIEW, never CLEAR.
5. Call `check_files` with the S1 file text. The result must equal `check_change` with S1 values on the verdict, `not_holding` and `verified_fixes`.
6. Call `check_files` with malformed YAML. Expect R_UNPARSEABLE.
7. **Read only proof.** Count nodes, edges and the `GraphState` properties before and after 5 checks; they must be identical. Run one check with `client.read` monkeypatched to fail on any write keyword; it must still pass.
8. A graph that is not ready returns the guard error.
9. Arguments over the limits, extra keys, path traversal (`../x`) and absolute paths are all rejected.
10. MCP: the existing stdio MCP test lists 11 tools and calls `check_change` with S1.
11. CLI exit codes are 2, 1 and 0 for S1, S4 and S1_FIXED.

### Acceptance
- Every test above passes and the whole suite stays green.
- Manual check: run the demo in Claude Code with the `CLAUDE.md` above. The agent calls `check_files` without being told to, and refuses the unsafe edit.

**Estimate:** 2 to 3 hours.

## F2. What if panel

### What it is
A page at `/what-if` where anyone can change registered fact values in the browser and see the impact immediately:
- the verdict;
- the reach graph turning red or green;
- the affected decisions and reviewers;
- the verified fixes.

It calls `POST /api/check` from F1, so the reasoning is identical to a real PR.

### UI
- Show a table of registered facts: id, file:line, current main value, owner team, `controlled_by` (external facts get a badge). Each row has an input.
- Add preset buttons loaded from `scenarios/scenarios.yaml`, covering S1, S1_FIXED, S6 and S12, labelled by scenario title. Presets only fill the inputs.
- On change, debounce by 400 ms, then post to `/api/check` and render:
  - a verdict badge;
  - the Mermaid reach graph, using `render.mermaid` on the server and returning the text. Reuse the pinned Mermaid import from `assessment.html` (`mermaid@11.12.1`, `securityLevel:'strict'`);
  - the `not_holding` table, with a link from each id to `/entities/<id>`;
  - decisions with reviewers shown by **name** (map ids to names on the server);
  - verified fixes, each with an "Apply fix" button that only fills the inputs and runs the check again.
- Put the state in the URL query (`?set=fact=value&set=...`) so a scenario can be shared as a link. Do not use browser storage.
- Show a fixed banner: "Hypothetical. Nothing is stored or posted."
- Add a navigation link "What if" in `base.html`.
- Match the existing style in `style.css`. No new JS framework, and no inline event handlers; add a `static/whatif.js` module.

### Server
- `GET /what-if` renders the template with the fact list. Add a new read query `registered_facts.cypher` returning id, file, line, key, value, value_type, controlled_by and owner.
- `POST /api/check`, from F1, also returns `mermaid` text and a `names` map.

### Tests
1. `GET /what-if` returns 200 and lists all 12 registered facts.
2. Posting S1 changes returns BLOCKED with 4 not_holding, and Mermaid text contains `G_DEDUPE`.
3. Posting the S1 fix values gives CLEAR.
4. An unknown fact or a bad body returns 422 with no stack trace.
5. Graph counts are unchanged after 10 posts.
6. Extend `scripts/check_ui.py` to load `/what-if?set=paylane.retry_window_hours=72`. Assert that the verdict badge reads BLOCKED and that the Mermaid SVG rendered, on desktop and mobile, with no console errors.

**Estimate:** 2 to 3 hours.

## F3. Knowledge steward: the brain asks humans to fix stale knowledge

### What it is
A sweep that finds decaying knowledge and opens one GitHub issue per problem in the **sandbox repo** (`SANDBOX_REPO`, kestrel-platform). The issue goes to the right people, and is updated or closed as the graph changes.

There are two finding kinds, both computed only from existing graph data:

| Kind | Source | Example |
| --- | --- | --- |
| `EXPIRED_ATTESTATION` | Manual assumptions whose state is `unverified` at `now`: the attestation expired, the attester is not active, or there is no attestation | A_RATES_SOURCE: Tess's attestation expired on 2026-09-30 |
| `ORPHANED_DECISION` | The `orphaned_decisions` query | ADR-012: Marco and Lena have left, nobody accountable is active |

**Each finding records:**
- the guarantees that depend on it (from `guarantee_assumption_pairs`, or the decision's provides and relies_on edges), with tier and current health;
- the decisions involved;
- the **reviewer candidates** from the existing `_route` logic, ranked by recent authored evidence;
- the source citations (`provenance`).

### Modes
- `premise steward`: dry run, which is the default. It prints the plan as JSON (create, update, close, unchanged) and makes no GitHub calls apart from reads.
- `premise steward --execute`: applies the plan.
- In the poller: run after `sync_main` only when the graph revision changed **and** `STEWARD_ENABLED=true`. It defaults to false.

### GitHub behavior
- Add a marker to each issue body: `<!-- premise:steward:<kind>:<entity_id> -->`.
- Find existing issues by listing `issues?state=all&creator=<actor>` with pagination, then match the marker. **Do not rely on labels**, because they may need extra permissions.
- **No issue and the finding exists:** create one titled `Premise: <entity> needs an owner` or `Premise: attestation for <assumption> expired`.
- **Open issue and the finding still exists:** update the body only if the rendered body changed.
- **Open issue and the finding is resolved:** comment `Resolved at graph revision N` and close the issue.
- **Closed issue and the finding still exists:** do **not** reopen it, because a human decided. Record it as `suppressed_by_human` in the plan.
- **Safety:**
  - At most 10 writes per run, then stop and report the rest.
  - Never `@mention` anyone; names go through `safe`, which already neutralizes `@`.
  - Never assign users; the fictional people have no GitHub accounts.
  - Never touch PRs or files.
- Record every write as a `StewardAction {id, kind, entity, status, issue_url, graph_rev, payload_json}` node, with the same begin, finish and reconcile pattern as `Store`. Add `Store.begin_task(key, kind, payload)` for this, because the existing `begin` requires an Assessment node.

### Issue body (deterministic)
1. What decayed, and since when.
2. Which guarantees now rest on it, with tier and health.
3. Which decisions are exposed.
4. Suggested reviewers, by name, with their evidence counts.
5. Exactly what to do, with the file and line to edit (from provenance). For example: renew the attestation in `adr/ADR-003.md` with a new `date` and `review_by`, or add an active approver to ADR-012.
6. Footer: graph revision, and the line "Generated by Premise from graph data; no model was used."

### Tests (`tests/test_steward.py`, using `httpx.MockTransport` like `test_github.py`)
1. Against `kestrel`, the dry run finds exactly {EXPIRED_ATTESTATION A_RATES_SOURCE, ORPHANED_DECISION ADR-012} and makes no write requests.
2. Execute creates 2 issues with markers. A second execute makes 0 writes, which proves it is idempotent.
3. After renewing the attestation in `repo_copy` and ingesting again, execute comments on and closes exactly that issue.
4. When the issue for a still active finding is closed, it is not reopened, and the plan says `suppressed_by_human`.
5. The write cap: with 12 synthetic findings, only 10 writes happen and the rest are reported.
6. Escaping: a person name containing `@x [y](http://z)` renders neutralized.
7. If the graph is not ready, no GitHub writes happen.
8. With `STEWARD_ENABLED=false`, the poller never calls the steward.

**Token:** the fine grained token needs **Issues: Read and write** on kestrel-platform. Document this in `docs/PUBLISH.md`.

**Estimate:** 3 to 4 hours. This feature is optional; see rule 2.

## Demo script additions (for the video)
1. **F1, 20 seconds:** in Claude Code, inside kestrel-platform, type "raise the Paylane retry window to 72 hours". The agent calls `check_files`, gets BLOCKED, and proposes the verified fix. Say: "The agent checks the company's decisions before writing code."
2. **F2, 10 seconds:** open `/what-if`, press the S1 preset and watch the graph turn red, then press "Apply fix" and watch it turn green.
3. **F3, 10 seconds, only if merged:** show the issue "ADR-012 needs an owner", which names Jun with 7 recent sources.

## Prompt to paste into Codex for each feature
> Read `docs/Premise_Main_Features_Spec.md`, section F<n>, and section 0. Create branch `feat/<name>` from `main`. Implement exactly that section, including every listed test. Do not change the files listed in rule 6. Run the full suite, `premise scenarios`, and `scripts/check_ui.py`, and report actual results, not expectations. Commit locally; do not push. List anything in the spec you could not do, and why.