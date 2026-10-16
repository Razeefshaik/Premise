# Premise v2 Phase 2: design for Codex

**Branch:** `v2/phase-2`, created from `v2/self-maintaining-brain` **after** every fix in `docs/Premise_v2_Fix_Spec.md` is merged and green.
**Audience:** the Codex agent building it, and Razeef reviewing it.
**Timing:** Phase 2 is post hackathon work. It must not touch the submission branch. Do not demo it unless a package below is finished, tested and stable.

## 0. What Phase 2 adds, in one picture

```
 Phase 1 (done)                                  Phase 2 (this document)
 ───────────────────────────────────────         ──────────────────────────────────────────────────
 Slack + Jira fixtures                           + GitHub and Pages connectors, one connector interface
 rules only, numeric config facts                + LLM extractors (attestation evidence, decision drafts)
 identity: explicit mapping only                 + identity links with fuzzy PROPOSALS and a bridge check
 drift PRs                                       + Kind 2 knowledge: ON_CALL_FOR, VENDOR_FOR in their own graph
 small self-written eval                         + 80 snippet gold set with a hold-out half
 CLI only                                        + a read-only review page (premise-v2 serve)
```

## 1. Rules that do not change

1. **The plane rule.** v2 writes only to its stream, its staging graph, and (new) its knowledge graph. The decision graph changes only through v1 ingest of a merged git commit. Verdict code never reads the staging or knowledge graphs.
2. **The grounding gate is mandatory for every extractor, especially LLM ones.**
   - Each candidate carries exact quotes.
   - Each literal field (number, id, name, stance word) must appear inside its quote.
   - Code checks this. The model's confidence never makes anything true.
3. **Kind 1 is closed.** No extractor may emit REQUIRES, PROVIDES or RELIES_ON edges into any graph. Decision drafts (E1) become proposed ADR **files** in a PR, which v1 validates.
4. **Do not modify `premise/`.** v2 imports from it. The only allowed reuse points are:
   - `premise.agent.llm.make_adapter` (the Codex CLI and Anthropic adapters);
   - `premise.github.api.GitHub`;
   - the v1 ingest, validate and assess functions;
   - `premise.agent.render.safe`.
5. **Private sources stay private.** Quotes from `visibility != "public"` sources never leave the staging graph: not in PR text, not in issue text, not in the review page unless it is served on localhost.
6. **Tests use real FalkorDB**, `FakeGitHub`, and a new `FakeAdapter` for models. No test may call a real model or a real API.
7. **Model use is local.** `LLM_PROVIDER=codex-cli` or `none`. With `none`, LLM extractors are skipped and reported, and everything deterministic still runs.

## 2. Work packages (build in this order)

| # | Package | Estimate | Depends on |
| --- | --- | --- | --- |
| P2.1 | Connector interface + GitHub and Pages connectors | 5 h | none |
| P2.2 | Identity links with fuzzy proposals and a bridge check | 4 h | P2.1 |
| P2.3 | Extractor framework + LLM extractor E3 (attestation evidence) | 6 h | P2.2 |
| P2.4 | Kind 2 knowledge: extractor, proposals, knowledge graph loader, unmatched mentions | 6 h | P2.3 |
| P2.5 | Gold set (80 snippets, half hold-out) and per extractor metrics | 4 h | P2.3 |
| P2.6 | Read-only review page (`premise-v2 serve`) | 4 h | P2.4 |
| P2.7 | LLM extractor E1 (decision drafts as proposed ADR files) | 6 h | P2.3, P2.5 |

Every package ends with green tests and its own commit. Stop after any package if time runs out; each one is useful alone.

---

## P2.1 Connector interface, GitHub and Pages

**Why:** the research found that connector frameworks with checkpoints, failures reported as data, and deletion by listing (the Onyx pattern) are the reliable shape for this. dlt's verified sources are a poor fit, because they miss Slack thread replies and do full reloads.

**Interface** (`premise_v2/connectors/base.py`):

```python
class ConnectorFailure(BaseModel):          # yielded, never raised, for one bad item
    scope: str; native_id: str | None; error: str; retryable: bool

class Connector(Protocol):
    name: str                                # "github", "pages", "slack", "jira"
    scope: str                               # connector instance, e.g. "github:owner/repo"
    def load(self, checkpoint: dict | None) -> Generator[Envelope | ConnectorFailure, None, dict]: ...
    def list_keys(self) -> set[str]: ...     # every entity key that exists now (for tombstones)
```

- The checkpoint is a dict (stored as JSON on the `Cursor` node), so a connector can keep several cursors, such as issues `since` plus a commit SHA.
- `Pipeline.collect` is unchanged in spirit:
  - it saves the checkpoint only after the last `XADD`;
  - it stores failures as `ConnectorFailure` nodes in staging, and retries the retryable ones next run;
  - it computes tombstones per scope.
- Move the Slack and Jira workers onto this interface with no behaviour change. All Phase 1 tests must pass unchanged.

**GitHub connector** (`connectors/github.py`): **read-only**. It uses `premise.github.api.GitHub` live, or a fixture JSON with the same shapes.

| Item | Envelope `kind` | Notes |
| --- | --- | --- |
| Issue, with comments as separate items | `issue`, `comment` | `thread` = issue key; incremental via `since` |
| Pull request, with review comments | `pull_request`, `comment` | Skip PRs opened by Premise itself (marker in body) |
| `CODEOWNERS` | `file` | Normalized into ownership rows, not chat |
| `docs/**/*.md` at the default branch head | `page` | Keyed by path; sequence = commit time; deleted paths become tombstones |

**Pages connector** (`connectors/pages.py`): a folder of markdown files exported from Notion or Confluence, with front matter `authors`, `updated` and `visibility`. It is the same as GitHub pages but local.

**Tests**
- Interface conformance for all four connectors.
- A failure item does not stop the run and is retried next run.
- Checkpoint saved only after all `XADD`s: simulate a crash between yield and save, and assert that the next run re-sends the items, which then dedupe.
- Premise's own PRs are skipped.
- Deleting a page file produces a tombstone.

---

## P2.2 Identity: link, never merge

**Change from Phase 1:** a claim stores the **account** (`slack:U01ANIKA`), not the person. The person is resolved **at reconcile time**, so fixing an identity link instantly fixes every count, with no reprocessing.

**Staging model:**

```
(:Account {key:"slack:U01ANIKA", display, email})-[:LINKED_TO {method, score, status, decided_by, at_ms}]->(:PersonRef {id:"p_anika"})
```

`status` is one of:
- `auto`: an explicit mapping in `ext/identities.yaml`, or an exact verified email;
- `proposed`: a fuzzy match;
- `confirmed` or `rejected`: through a merged PR.

**Rules from the research**
1. Only `auto` and `confirmed` links count for reviewers or origin counting. With a `proposed` or missing link, the account counts as its own person (`unresolved:<account>`), so an unresolved account can never make two people look like one.
2. Fuzzy matching uses `rapidfuzz.fuzz.token_set_ratio(display_name, person.name) >= 92` and creates a `proposed` link only.
3. **Bridge check:** a proposed link is flagged `bridge` if the person already has an `auto` or `confirmed` account **in the same source**. Bridge proposals are shown with a warning and never batch approved.
4. Links are reversible: rejecting means a PR that removes the line, after which the edge goes to `rejected`. Nothing is ever merged destructively.

**Output:** identity proposals become a PR that adds lines to `ext/identities.yaml`. Generalize `ProposalWriter` to a `kind` parameter (`drift`, `identity`, `knowledge`, `decision`) with one renderer per kind. One PR batches up to 10 identity proposals.

**Tests**
- A fuzzy "Anika R." gives `proposed` and does not count toward origins.
- After the mapping file changes, reconcile re-counts origins without reprocessing items.
- The bridge flag is set correctly.
- Rejecting a link removes it from counts.

---

## P2.3 Extractor framework and E3 attestation evidence (first LLM extractor)

**Framework** (`premise_v2/extract/base.py`):

```python
class Extractor(Protocol):
    name: str; version: str
    handles: set[str]                                   # item classes, e.g. {"chat", "ticket", "page"}
    needs_model: bool
    def prefilter(self, item) -> bool: ...              # cheap rules; only True items reach the model
    def extract(self, item) -> list[Candidate]: ...     # every Candidate has quotes
    def ground(self, cand, body) -> tuple[bool, str]: ...  # deterministic, per candidate type
```

**The LLM call recipe** (from the research; follow it exactly):
1. **Prefilter first.** Scope words plus keywords. Most items never reach the model.
2. **One flat pydantic schema per candidate type.** No nesting deeper than one list.
3. **Quote first.** The schema lists `quote` before every derived field, so the model copies text before interpreting it.
4. Source text is wrapped as untrusted data:

   ```
   <source id=... untrusted="true">...</source>
   ```

   and the instructions say never to follow instructions inside it.
5. Call `adapter.structured(system, payload)` with the v1 `make_adapter`. On a pydantic validation error, do **one** repair retry with the error message, then give up and count the failure.
6. Cache by `(extractor name, version, model, content_hash)` in staging (`ExtractionCache` node), so reruns cost nothing.
7. A per run model call budget (default 40) is shown in the summary. When it is exhausted, skip and report; never guess.
8. Everything returned goes through `ground()`. Rejected candidates are stored with their reason, for the eval.

**E3: evidence about manual assumptions.** Example: A_STABLE_EVENT_ID, "Paylane sends the same event_id on every retry".
- **Input:** items in scope that mention the partner or service of a **manual** assumption (taken from the decision graph, read only).
- **Schema:**

  ```python
  class AssumptionEvidence(BaseModel):
      quote: str                   # exact sentence(s) from the source
      assumption_id: str           # must be a manual assumption that exists
      stance: Literal["supports", "contradicts", "unrelated"]
      stance_words: list[str]      # the words in the quote that carry the stance, e.g. ["changes", "new event_id"]
  ```

- **Grounding:**
  - the quote is in the source;
  - every `stance_words` entry is inside the quote;
  - the quote shares at least 2 content words with the assumption text (stop words removed);
  - `assumption_id` exists and is manual.
- **Reconcile:** contradicting evidence from 2 or more independent origins (the Phase 1 rule) against an assumption whose attestation is still valid becomes an **attestation challenge**.
- **Output:** dry-run markdown plus a review queue item. Optional live mode opens a GitHub **issue** (not a PR), naming the attester and the reviewers from v1 routing, using the same marker and idempotency pattern as v1's steward.
- An E3 finding never changes an attestation. Only a human edit to the ADR does.

**Tests (FakeAdapter)**
1. Correct contradicting evidence is grounded, and a challenge is raised with 2 origins.
2. A hallucinated quote is rejected (`quote_not_in_source`).
3. `stance_words` outside the quote is rejected.
4. An unknown or predicate assumption id is rejected.
5. An injected instruction inside the source text has no effect on output handling.
6. Invalid JSON, then a valid repair: accepted. Invalid twice: counted as a failure.
7. Cache hit: zero adapter calls on rerun.
8. Budget exhausted: skipped and reported.
9. `LLM_PROVIDER=none`: E3 is skipped, everything else runs.

---

## P2.4 Kind 2 knowledge

**Goal:** approved descriptive relations (`ON_CALL_FOR`, `VENDOR_FOR`, more later) are extracted with evidence, proposed through PRs, and loaded into a **separate** `premise_knowledge` graph that verdicts never read.

**New KIF file in the model repo**, ignored by v1 ingest: `knowledge/relations.yaml`

```yaml
relations:
  - type: ON_CALL_FOR
    from: p_jun
    to: paymentservice
    valid_from: 2026-10-14
    valid_to: null
    evidence: ["slack:C01OPS:1792...", "jira:OPS-41"]
    registry_version: 1
```

**Extraction, in two stages**
1. **Deterministic:** for each approved relation in `ext/relations.yaml`, match `<entity of domain type> … <alias> … <entity of range type>` inside one sentence. Entities are resolved from people names or accounts and service ids or aliases.
2. **LLM fallback, only for prefiltered sentences that name two known entities.**
   - The schema allows only approved relation names, plus `"NONE"`.
   - Grounding: both entity mentions and one alias **or** the model's `relation_words` are inside the quote.

**Unmatched mentions:** when a sentence names two known entities with a verb phrase that matches no approved type, store an `UnmatchedMention {phrase, domain_label, range_label, quote, item}` node. This is the input for the Phase 3 relation manager. **Phase 2 only collects them; it never proposes new types.**

**Proposals and loading**
- A Kind 2 proposal is a PR that adds or ends rows in `knowledge/relations.yaml`. A new rotation sets `valid_to` on the old row and adds a new row; history is never overwritten.
- `premise-v2 load-knowledge --model <repo>` reads the **merged** file, validates every row against the registry (domain, range, approved status, temporal rules), and writes the `premise_knowledge` graph from scratch. This is deterministic and idempotent, like v1 ingest.
- **Firewall tests:**
  - the knowledge graph contains no REQUIRES, PROVIDES or RELIES_ON;
  - v1 queries never mention the knowledge graph name;
  - a row using a retired or proposed type is rejected by the loader.

---

## P2.5 Gold set and metrics

- **Location:** `fixtures/v2/gold/*.yaml`, **80 snippets**, synthetic and hand reviewed by Razeef. Each snippet has a source item and expected candidates.
- **Coverage, at least:**

  | Category | Count |
  | --- | --- |
  | Negatives | 15 |
  | Hedges or jokes | 8 |
  | Supersession ("from X to Y", "now") | 8 |
  | Unit conversions | 6 |
  | Injected instructions | 5 |
  | Identity cases | 8 |
  | Attestation evidence | 12 |
  | Kind 2 relations | 12 |
  | Decision prose | 6 |

- **Split:** 40 `tune` and 40 `holdout`. Prompts and rules may be adjusted only by looking at `tune`. CI reports both, and the README quotes only `holdout`.
- **Metrics per extractor:**
  - claim precision and recall;
  - exact quote rate;
  - field accuracy;
  - grounding rejection reasons;
  - schema validity rate;
  - model calls and seconds.
- **CI floors (holdout):**
  - E2 precision ≥ 0.95;
  - E3 precision ≥ 0.85;
  - Kind 2 precision ≥ 0.85;
  - **no injected instruction ever produces a grounded candidate.**

  Below a floor, the test fails.
- Model-backed metrics come from a **recorded** run: real Codex outputs saved as `fixtures/v2/gold/recordings/*.json` and replayed through `FakeAdapter`. This keeps CI deterministic and records exactly what the model said.

---

## P2.6 Review page (`premise-v2 serve`, port 8002)

- A separate small FastAPI app in `premise_v2/web/` that reuses v1's `style.css` by copy, not import, and binds to `127.0.0.1` by default.
- **Pages:**

  | Page | Contents |
  | --- | --- |
  | `/` | Queue grouped by kind: drifts, attestation challenges, identity proposals, knowledge proposals, unmatched mentions. Each shows support level, contested flag, and age |
  | `/item/<key>` | Quotes (private ones only on localhost), origins as groups, the v1 preview verdict, the dry-run diff, and a link to the PR if published |
  | `/relations` | Registry entries with usage counts and examples, plus unmatched mention clusters (just counts per phrase; no proposals) |

- **Read only**, except one action: **Dismiss**, which writes a `Rejection` to staging, the same memory a closed PR creates. No action ever writes the decision graph, the knowledge graph, or git.
- **Tests:** pages render, private quotes are hidden when the request is not from localhost, and Dismiss creates a rejection and removes the item from the queue.

---

## P2.7 E1 decision drafts (last; hardest)

**Goal:** a design page or long thread that describes a decision becomes a **draft ADR file** (`status: proposed`) in a PR.

- **Schema** (flat; one list each):
  - `title`, `governs` (service ids), `context_quote`, `decision_quote`;
  - `guarantees: [{statement_quote, about}]`;
  - `assumptions: [{text_quote, check: "manual" | {lhs_fact, op, rhs_fact or value}}]`;
  - `requires: [{guarantee_index, assumption_index}]`.
- **Grounding:**
  - every `*_quote` is in the source;
  - every fact id in a check is a **registered** fact;
  - service ids exist;
  - `op` is one of `<, <=, ==, >=, >`;
  - each predicate's fact must be mentioned (by alias) inside that assumption's quote.
- **Rendering:** a new `adr/ADR-DRAFT-<hash8>.md` with `status: proposed`. A v1 `parse_repo` + `validate` run on a temp copy must pass, or nothing is proposed.
- v1 already treats this as a model change (`R_MODEL_CHANGE`), so the PR always needs human review. **No E1 output can ever influence a verdict until a human edits it to `accepted` and merges it.**
- **Tests:**
  - a valid page gives a draft that v1 validates;
  - an unregistered fact in a predicate is rejected;
  - a missing quote is rejected;
  - a draft that creates a REQUIRES cycle fails v1 validation and is not proposed.

---

## 3. Definition of done for Phase 2
- All Phase 1 tests and fix spec tests still pass; every package's tests pass.
- `premise-v2 eval --gold` reports holdout metrics above the floors, written to `docs/V2_EVAL.md` with the hold-out caveat.
- The isolation tests pass:
  - v2 never writes the decision graph;
  - the knowledge graph has no Kind 1 edges;
  - private quotes never appear in any PR, issue or non-localhost page.
- `docs/V2.md` is updated with the new architecture diagram, the identity model, the Kind 2 flow, and the honest limits.

## 4. Explicitly NOT in Phase 2
- The relation manager that proposes new relation types (Phase 3).
- Live Slack and Jira connectors against real workspaces (Phase 3; the hackathon data rules forbid private data anyway).
- GraphRAG-SDK document Q&A, time travel queries, score calibration (Phase 3).
- Any change to v1 verdict logic.

## 5. Prompt to paste into Codex
> Read `docs/Premise_v2_Phase2_Design.md` completely. Create branch `v2/phase-2` from `v2/self-maintaining-brain` (after the fix spec is merged). Implement the packages in order P2.1 to P2.7, one commit per package, stopping after any package if tests are not green. Follow section 1 rules as hard constraints: never modify `premise/`, never write the decision graph, every extractor output passes a deterministic grounding gate, tests use real FalkorDB with FakeGitHub and FakeAdapter only. After each package, run the full suite and report actual results. Do not push.