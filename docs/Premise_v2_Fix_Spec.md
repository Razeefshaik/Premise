# Premise v2 Phase 1: fix spec for the 8 review findings

**For:** the Codex agent working on branch `v2/self-maintaining-brain` (base commit `5f60595`).
**Source:** `.runtime/v2-review/REVIEW.md`. All 8 findings are confirmed against the code.

**Rules**
- Fix only what is listed. Do not touch `premise/` (v1).
- Every fix needs a regression test in `tests/test_v2_*.py` that fails before the fix and passes after, using real FalkorDB and the existing `FakeGitHub`.
- At the end, run the full suite, `premise-v2 registry-check` and `premise-v2 eval`, and report the actual results.

Recommended order: 1, 2, 4, 3, 7, 8, 5, 6. Privacy and safety come first; the proposal lifecycle comes last because 5 and 6 share code.

---

## Fix 1 (P1): graph name isolation in every command

**Bug:** `reset` compares `--decision-graph` with v1's graph name but deletes the **staging** graph, so a staging name equal to v1's graph slips through. `run` and `eval` have no checks at all.

**Design:** add one function in `premise_v2/cli.py` (or a new `premise_v2/safety.py`):

```python
def check_isolation(staging: str, decision: str, protected: set[str]) -> list[str]:
    errors = []
    if staging == decision: errors.append("staging and decision graphs must differ")
    for name, role in ((staging, "staging"), (decision, "decision")):
        if name in protected: errors.append(f"{role} graph '{name}' is protected (used by v1)")
    return errors
```

- `protected` = `{settings().graph_name, "premise_codex_demo"}`, plus anything in an optional env var `V2_PROTECTED_GRAPHS` (comma separated).
- Call it at the top of `main()` for **every** subcommand except `registry-check`, before any connection, setup, ingest or deletion. On error, print the errors and exit with code 2.
- `reset` deletes only the staging graph and the v2 stream keys, as today. The check now covers the graph it actually deletes.

**Tests**
1. `reset --staging-graph <v1 name>` exits 2, and a sentinel graph with that name still exists.
2. `run` with staging equal to decision exits 2, and nothing is created.
3. `run --decision-graph premise_codex_demo` exits 2.

---

## Fix 2 (P1): private quotes in every PR section

**Bug:** only supporting evidence checks `visibility`. Disagreeing and weak evidence print private quotes into the PR body.

**Design:** in `premise_v2/propose.py`, add one helper and use it for **all three** sections:

```python
def quote_of(e) -> str:
    return safe(e["quote"]) if e.get("visibility") == "public" else "(private source; quote withheld)"
```

Also make sure `_evidence()` in `reconcile.py` copies `visibility` for every claim (it does today; keep a test on it). Treat a missing visibility as **private**, never public.

**Test:** a private channel fixture with one supporting, one negated and one hedged message. Assert that none of the three private texts appear in the rendered body, and that the "withheld" text appears 3 times.

---

## Fix 3 (P1): each connector owns its own cursor and deletions

**Bug:** all Slack files share the cursor `slack` and compare their own listing against **every** Slack item. A second channel deletes the first channel's evidence, and a newer cursor from one file skips older messages in another.

**Design**
- Add an optional field `scope: str | None` to `Envelope`. It names the connector instance that owns the item.
- Each worker exposes a `scope` property:
  - `SlackFixtureWorker`: `f"slack:{channel_id}"`;
  - `JiraFixtureWorker`: `f"jira:{path.stem}"`.

  Workers set `scope` on every envelope they yield.
- `Staging.store_item` stores `i.scope`, and `tombstone` keeps it.
- `Staging.live_keys(scope)` filters by `i.scope = $scope` instead of `i.source`.
- In `Pipeline.collect`:
  - the cursor key is `w.scope`, not `w.name`;
  - tombstones are computed as `live_keys(w.scope) - w.list_keys()`, and the tombstone envelope carries `scope=w.scope`.

**Tests**
1. Two Slack fixture files with different channel ids. Run twice with unchanged files: 0 tombstones, and all items still live.
2. File A has newer timestamps than file B. Both files' messages are collected on the first run.
3. Removing one message from file A tombstones exactly that message and nothing in file B.

---

## Fix 4 (P1): a root and its reply are one origin

**Bug:** a reply joins `thread:<root>`, but the root itself never joins `thread:<root>`. With different authors, root plus reply count as 2 independent origins.

**Design:** in `reconcile._origins`, give every claim one canonical thread node:

```python
uf.union(k, f"thread:{c.get('item_thread') or k}")
```

A reply's thread is its root; a root's thread is itself. Both land on the same node. Keep the existing person and cross link unions. For Jira, the canonical thread of `jira:PAY-311#10001` is `jira:PAY-311`; that is already true through `item_thread`.

**Test:** root by Anika ("Paylane now retries for 72 hours") plus a reply by Ravi in the same thread ("yes, 72 hours"), and no other evidence. Expect `support == "observed"`, 1 origin, and the proposal skipped.

---

## Fix 7 (P2): a no-op edit must move the version watermark

**Bug:** a newer version with identical text is treated as a duplicate without recording its sequence, so a delayed older version is then accepted.

**Design**
- Add `Staging.advance_version(key, seq)`:

  ```cypher
  MATCH (i:Item {key:$k}) WHERE i.sequence < $s SET i.sequence=$s, i.processed_seq=$s
  ```

- In `Gateway.process`, in the "same content and processed" branch, call `advance_version` when `env.sequence > latest["sequence"]` before returning `duplicate`.
- Claims keep their original sequence; that is fine, because the text did not change.

**Test:** process v1 = "72 hours", then v3 with identical text, then a delayed v2 = "48 hours". v2 must be `stale`, and the active claim stays 72.

---

## Fix 8 (P2): crash recovery must read the whole pending list

**Bug:** the consumer reads only the first page of its own pending entries and ignores XAUTOCLAIM's continuation cursor. With 201 pending entries only 100 are recovered, and reconciliation runs on partial data.

**Design** for `EnvelopeStream._batches`:
1. **Own pending, paged:** start at `after = "0"`, then loop `XREADGROUP ... STREAMS stream <after>`. After each page set `after` to the last entry id, and stop on an empty page.
2. **Other consumers' idle entries:** loop `XAUTOCLAIM` from cursor `"0-0"`, passing back the returned cursor each time, until it returns `0-0`.
3. **New entries:** `>` until empty, as today.

In `consume`, keep a `tried` set of entry ids, so each entry is tried **at most once per run**. A failing handler cannot spin, and step 2 cannot retry what step 1 already tried.

`consume` returns `pending_after`, the result of `XPENDING` after the run. `Pipeline.run` records it in the summary. If it is greater than 0, the summary sets `caught_up: false`, and **the proposal step is skipped** for that run, with the reason "stream not caught up".

**Tests**
1. 201 entries are read by consumer A without being acknowledged. One `consume("A")` with `count=100` processes all 201, leaving `pending == 0`.
2. The same test through a different consumer, with `min_idle_ms=0`: all 201 are reclaimed.
3. One poison entry among 50 good ones: the 50 succeed, the poison entry is tried once per run, and it is dead lettered on the third run.

---

## Fixes 5 and 6 (P2): the proposal lifecycle

These two share one design. A proposal needs two separate facts:
- what the **document** says (`body_hash`);
- whether it is **published** (`pr_url`, `remote_state`).

Store both on the `Proposal` node:

| Field | Meaning |
| --- | --- |
| `status` | `open`, `withdrawn`, `merged` or `rejected` (local lifecycle) |
| `body_hash` | Hash of the last rendered body |
| `pr_url`, `pr_number` | Set only after GitHub confirmed the PR |
| `published_hash` | `body_hash` of the version last sent to GitHub |

### Fix 5: a dry run must not block a later live run

**Bug:** the dry run stores `body_hash` and `status=open`, so a later live run sees `unchanged` and never opens the PR.

**Design:** in `ProposalWriter.write`, publish when a GitHub client is present **and** any of these holds:

```python
needs_publish = self.github is not None and (
    not existing or not existing.get("pr_url")              # never published (dry run before)
    or existing.get("status") != "open"                     # was withdrawn and evidence came back
    or existing.get("published_hash") != digest)            # body changed since last publish
```

After a successful publish, store `pr_url`, `pr_number` and `published_hash = digest`. A dry run never sets these.

**Test:** run a dry run, then a live run on the same staging graph. Exactly 1 PR is created and `pr_url` is stored. A third live run makes 0 GitHub writes.

### Fix 6: withdraw proposals whose evidence is gone

**Bug:** when supporting claims are deleted or edited away, the drift disappears and the old PR stays open with stale quotes.

**Design:** add `ProposalWriter.withdraw(key, reason)`, and call it from `Pipeline.run` after writing current proposals:

```text
current = { keys of drifts whose proposal state is created / updated / unchanged }
for every Proposal with status 'open' and key not in current:
    reason = "no remaining evidence"                    if the drift no longer exists
           = "evidence now has only one independent origin"   if it exists but is only observed
    withdraw(key, reason)
```

`withdraw` does the following:
- sets `status = withdrawn`, `withdrawn_reason`, and `withdrawn_ms`;
- if the proposal has a PR and a GitHub client is present, it PATCHes the PR body with a banner at the top:

  > **Withdrawn by Premise v2:** <reason>. The evidence listed below is no longer current.

  and then closes the PR (`state: closed`);
- it does **not** create a Rejection, because a human did not reject it;
- `sync_outcomes` only looks at `status = open`, so withdrawn PRs are never misread as human rejections.

If evidence returns later, Fix 5's `status != "open"` rule opens a **new** PR. GitHub will not reuse a closed PR for the same branch, so `_open_pr` must POST a new PR when no open PR exists for the head; it already does.

**Tests**
1. Live run, then tombstone every supporting item, then rerun. 0 drifts; the proposal is `withdrawn`; the fake PR is closed and its body starts with the banner; no Rejection node exists.
2. Delete Anika's messages only, so 1 origin remains. The proposal is withdrawn with the "one independent origin" reason.
3. Restore the evidence. A new PR is opened (PR number 2), and status is `open` again.
4. Dry run only (no GitHub): withdrawal changes local status, and no GitHub calls happen.

---

## Extra (small): a friendly error when FalkorDB is unreachable

In `premise_v2/cli.py`, wrap the subcommands in `try/except GraphUnavailable` and `redis.exceptions.ConnectionError`/`TimeoutError`. Print one line and exit with code 3:

```text
Cannot reach FalkorDB at <host>:<port>. Start it with: docker compose up -d falkordb
(check FALKORDB_HOST in .env: use 127.0.0.1 when running on Windows, not "falkordb")
```

**Test:** run with port 1. The command exits with 3, and the output contains "Cannot reach FalkorDB" and no traceback.

---

## Done means
- All 8 findings plus the extra have a test that failed before the fix.
- The full suite passes (196 plus the new tests), `registry-check` passes, and `premise-v2 eval` still reports 10/10 claims, 1/1 drift, 0 decoys and 4/4 grounding probes.
- Run the review's `probes.py` again; every probe now shows the fixed behaviour.
- Update `docs/V2.md`: proposal states (`open`, `withdrawn`, `merged`, `rejected`) and per connector scopes.

## Prompt to paste into Codex
> Read `docs/Premise_v2_Fix_Spec.md` completely. On branch `v2/self-maintaining-brain`, implement every fix in the recommended order, each with the listed regression tests, using real FalkorDB and the existing FakeGitHub. Do not modify anything under `premise/`. After each fix, run the v2 tests. At the end, run the full suite, `premise-v2 registry-check`, `premise-v2 eval`, and `.runtime/v2-review/probes.py`, and report actual results. Commit each fix separately with a clear message. Do not push.