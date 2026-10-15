# Premise: Implementation Specification

**Event:** WeMakeDevs x FalkorDB Graph Hacks (Oct 15 to 18, 2026)
**Tracks entered:** Track 3 (Company Brain) and Track 1 (Agents That Act on Connected Data)
**Spec date:** Oct 16, 2026, 02:00 IST. **Revision 2:** Oct 16, 03:45 IST (three review corrections, milestone 1 implemented and tested)
**Submission target:** Oct 18, 21:00 IST (hard deadline 23:59 IST)
**Status:** Final. Every decision in this document is locked unless a test in section 13 proves it wrong.
**Revision 2 changes:** (1) manual assumptions hold only with a current attestation by an active person (D12); (2) verdicts and fixes are judged on every prerequisite of every affected guarantee, including unchanged facts, and "checked and not affected" requires an actual evaluation (D13); (3) LLM calls send no sampling parameters, follow the verified Claude Sonnet 5.5 request rules, and get reproducibility from caching and deterministic fallbacks (D14). Sections changed: 0, 3.2, 4.2, 5.1 to 5.3, 5.7, 6, 7.2, 7.4, 7.6 (new), 9, 12.3, 12.5, 13, 14, 15.

---

## 0. Summary and locked decisions

**Premise checks every code change against the guarantees your engineering decisions depend on.**

Decisions (ADRs) declare the **guarantees** they promise and the guarantees they rely on. Each guarantee declares exactly what it **requires**: other guarantees and **assumptions**. Assumptions are either machine checkable predicates over configuration **facts** in the repo, or manual statements. When a pull request changes a fact, Premise evaluates the affected assumptions, propagates failures through guarantee requirements only, finds every decision that promises or relies on a broken guarantee, routes the review to someone still accountable, posts a gating commit status and an explanation on the PR, and has an agent search for a fix that it proves against the graph before opening it as a pull request. The same graph answers Company Brain questions with permalinks to source lines, through a web page and an MCP server.

### Locked decisions

| # | Decision |
| --- | --- |
| D1 | Failures propagate only along `Guarantee -[:REQUIRES]-> Guarantee or Assumption`. There is no `BUILDS_ON`. Decisions attach to guarantees through `PROVIDES` and `RELIES_ON` and never propagate failure themselves. |
| D2 | Guarantee semantics are AND over requirements, with three valued logic: broken dominates unknown, unknown dominates holds. |
| D3 | The blocking decision is a deterministic comparison evaluated in Cypher. No LLM output can fail or pass a check. |
| D4 | A PR never mutates the main graph's facts. Its changes are an overlay passed to the evaluator. |
| D5 | Derived health (assumption, guarantee, decision status) is never stored. It is always computed by query from current facts. Only authored lifecycle state (`Decision.status`) is stored. |
| D6 | FalkorDB is the only datastore. Cursors, revisions, assessments, and action logs all live in the graph. |
| D7 | Ingestion is deterministic. No LLM is used to build the graph in the MVP. |
| D8 | GitHub is the only external system. Real actions: commit status, one upserted PR comment, a stacked fix PR. Nothing else is claimed as sent. |
| D9 | Stack: Python 3.12, FastAPI, Jinja2, official `falkordb` client, `httpx`, PyYAML, pydantic v2, official `mcp` SDK, official `anthropic` SDK, pytest, git CLI, Docker Compose. No agent framework, no frontend framework, no embeddings in the MVP. |
| D10 | Two public repos: `premise` (the product, the submission) and `kestrel-platform` (the synthetic company where PRs happen). |
| D11 | If organizers confirm one track per submission, enter **Track 1**. |
| D12 | A manual assumption holds only with a current attestation (`ATTESTED` edge from an active person, dated on or before now, review date not passed). Otherwise it is **unverified**, which makes every guarantee that requires it **unknown**, never healthy. |
| D13 | A guarantee is judged on **all** of its prerequisites. Assessments and fix verification evaluate the full `REQUIRES` closure of every affected guarantee (unchanged facts and attestations included). "Checked and not affected" lists only decisions whose guarantee was evaluated and holds. |
| D14 | LLM requests to `claude-sonnet-5-5` send no `temperature`, `top_p`, or `top_k`, no forced `tool_choice`, no assistant prefill, and never `thinking: disabled` (all return 400). Reproducibility comes from the LLM never deciding verdicts, a response cache for demo replays, and deterministic fallbacks. |

---

## 1. Product definition

### 1.1 Problem

Engineering organizations record decisions but not the guarantees those decisions promise, nor the assumptions each guarantee needs. When a fact in the system changes (a partner extends its retry window, a timeout is raised), the decisions that silently depend on it keep governing production. Code review and CI check syntax and tests, not whether a change invalidates the reasoning behind other teams' decisions. Search cannot help because the dependent decisions never mention the changed fact.

### 1.2 Target user

The staff or principal engineer who owns architecture review in a 50 to 500 engineer organization that already writes ADRs. Secondary: engineering managers handling departures, and any engineer asking "why is this built this way, is that still true, and who owns it now?"

### 1.3 Why guarantees instead of BUILDS_ON (the fix)

`ADR-016 BUILDS_ON ADR-007` says nothing about **which part** of ADR-007 matters. ADR-007 promises two things: deduplication of partner webhooks, and fast acknowledgement of them. ADR-016 (mute delivery failure alerts) relies only on fast acknowledgement. With `BUILDS_ON`, a change that breaks deduplication would flag ADR-016, which is a false alarm. With guarantees:

```
ADR-007 -PROVIDES-> G_DEDUPE   -REQUIRES-> A_RETRY_WINDOW   (broken)
ADR-007 -PROVIDES-> G_ACK_FAST -REQUIRES-> A_ACK_BEFORE_TIMEOUT (holds)
ADR-016 -RELIES_ON-> G_ACK_FAST                                   => not affected
ADR-012 -RELIES_ON-> G_DEDUPE                                     => affected
```

Precision is now a testable property (test T5), and the PR comment shows it explicitly in a "checked and not affected" section.

### 1.4 Track mapping

| Official focus item | Premise feature |
| --- | --- |
| T3: Knowledge from docs, tickets, and chats in one graph | ADRs, configs, catalog, runbooks, tickets, and chat become Sources and Passages linked to services, decisions, guarantees, people |
| T3: Who owns what, and who knows what | Team OWNS Service; Person ACCOUNTABLE_FOR Decision; who_knows from authored passages mentioning a service |
| T3: Tracing decisions back to their source | Every decision, guarantee, assumption, fact, and authored edge carries a source file and line; every answer renders permalinks |
| T3: Keeping knowledge current | Main branch ingestion produces a new graph revision; health is always computed from current facts; open PRs are reassessed on every revision |
| T3: Answers with clear sources | Analyst Q&A and MCP tools return paths and permalinks; ids in answers are verified against tool rows |
| T1: Multihop reasoning | Fact to assumption to guarantee chain (up to 6) to decisions to services to callers (up to 3) to people |
| T1: Graph queries and algorithms as agent tools | Fixed typed Cypher tools, PageRank over guarantees, fulltext search |
| T1: Tool selection through MCP | Read tools exposed through an MCP server; demo in Claude Desktop |
| T1: Actions based on what the graph shows | Gating commit status, PR comment, verified fix PR |
| T1: Explainable results | Every verdict lists reason codes, witness chains, and source permalinks |

### 1.5 What fails without FalkorDB

The app holds no other state. Every verdict input is a Cypher result. If FalkorDB is unreachable or mid ingestion, Premise posts commit status `error` ("assessment unavailable") and takes no other action (test T16). Recursive SQL could emulate parts of this; the claim is that the product runs on graph traversal, graph algorithms, and fulltext over one graph, not that nothing else could.

---

## 2. Architecture

### 2.1 Components

```
  kestrel-platform (GitHub, public)                      premise (this repo)
  +------------------------------+     poll 15s     +--------------------------------------------+
  | main branch: company as code |<-----------------| Poller (asyncio task in the API process)   |
  | open PRs                     |                  |   main sha changed -> Ingestor             |
  | branch protection requires   |                  |   PR head changed  -> Assessor             |
  |   premise/decisions          |                  +--------------------------------------------+
  +------------------------------+                         |                    |
          ^         git fetch (read)                       v                    v
          |                                        +---------------+   +-------------------------+
          |  REST (write): statuses, comments,     | Ingestor      |   | Assessor (deterministic)|
          |  refs, contents, pulls                 | parse, check, |   | intake -> E1 -> Q2 ->   |
          +----------------------------------------| load, sweep   |   | Q3 -> policy            |
                         Executor                  +---------------+   +-------------------------+
                            ^                              |                    |
                            |                              v                    v
                    +----------------+             +--------------------------------------------+
                    | Fix agent      |<----------->|                FalkorDB                    |
                    | LLM proposes,  |  test_fix   |  graph premise_kestrel: domain + memory    |
                    | graph verifies |             |  GraphState, Assessment, Action            |
                    +----------------+             +--------------------------------------------+
                                                           ^                    ^
                                        +------------------+--+        +--------+-----------+
                                        | Web UI (FastAPI,    |        | MCP server (stdio) |
                                        | Jinja, Mermaid)     |        | read tools only    |
                                        | Analyst Q&A         |        | Claude Desktop     |
                                        +---------------------+        +--------------------+
```

### 2.2 Processes

| Process | Command | Notes |
| --- | --- | --- |
| falkordb | Docker image, pinned tag | Browser on port 3000 for debugging and video |
| app | `premise serve` | FastAPI on 8000; starts the poller task; one assessment at a time (global lock) |
| mcp | `premise mcp` | Spawned by Claude Desktop over stdio; read only connection |
| cli | `premise ingest / assess / health / ask / reconcile / reset` | Every pipeline step runnable without the poller, for tests and rehearsal |

### 2.3 Data flow per event

1. **Main changes:** `git fetch`, check out the new sha into a worktree, parse, validate, load as revision R+1, sweep stale domain edges, set `GraphState.rev = R+1`, mark every open PR stale, reassess them.
2. **PR head changes:** post status `pending` ("assessing"), compute overlay from the PR's own diff, evaluate, propagate, route, decide, run the fix agent, render, recheck staleness, execute actions, record.

---

## 3. The company as code (sandbox repo formats)

### 3.1 Layout of `kestrel-platform`

```
company/people.yaml
company/teams.yaml
catalog/services.yaml
facts.yaml
config/partners/paylane.yaml
config/partners/emailprovider.yaml
config/platform/redis.yaml
config/webhookingress.yaml
config/paymentservice.yaml
config/checkoutservice.yaml
config/emailservice.yaml
config/currencyservice.yaml
config/adservice.yaml
config/cartservice.yaml
adr/ADR-003.md ... adr/ADR-020.md
docs/runbooks/*.md
tickets/tickets.jsonl
chat/chat.jsonl
README.md   (states that the company, people, and partners are fictional)
```

"Model files" are `adr/*`, `facts.yaml`, `catalog/*`, `company/*`. A PR touching them is evaluated for its fact changes but always gets at least NEEDS_REVIEW (reason `R_MODEL_CHANGE`), because decision model edits are only applied after merge.

### 3.2 ADR front matter (the product's interface)

```yaml
---
id: ADR-012
title: Payment service skips its own idempotency check
status: accepted            # proposed | accepted | superseded
decided: 2026-02-10
authors: [p_marco]          # ACCOUNTABLE_FOR {role: author}
approvers: [p_lena]         # ACCOUNTABLE_FOR {role: approver}
governs: [paymentservice]
supersedes: [ADR-010]
relies_on: [G_DEDUPE]       # guarantee ids only
provides:
  - id: G_CHARGE_ONCE
    statement: A customer is charged at most once per order
    about: [paymentservice]
    requires: [G_DEDUPE]    # guarantee or assumption ids
assumptions: []             # assumptions this ADR declares (may be required by guarantees anywhere)
---
# body: context, decision, consequences (free text, chunked into passages)
```

An assumption entry:

```yaml
assumptions:
  - id: A_RETRY_WINDOW
    text: Paylane stops retrying before our dedupe records expire
    check: { lhs: paylane.retry_window_hours, op: "<=", rhs: webhook.dedupe_ttl_hours }
  - id: A_RATE_TTL
    text: Cached currency rates are never older than an hour
    check: { lhs: currency.cache_ttl_minutes, op: "<=", rhs_const: 60 }
  - id: A_STABLE_EVENT_ID
    text: Paylane sends the same event_id on every retry
    check: manual
    attestation:
      by: p_anika              # must be an active person at assessment time
      date: 2026-09-02         # not `on:` (YAML 1.1 reads `on` as the boolean true; ingestion rejects it)
      review_by: 2027-03-01    # after this date the assumption is unverified again
      evidence: Paylane API reference v3, section Event delivery
```

A manual assumption without an attestation, with an expired one, with a future date, or attested by someone who has left or is on leave is **unverified** (section 5.1).

Operators: `<`, `<=`, `==`, `>=`, `>`. Operands: fact against fact, or fact against a numeric or string constant. Strings support `==` only.

### 3.3 `facts.yaml`

```yaml
facts:
  paylane.retry_window_hours:
    file: config/partners/paylane.yaml
    key: retry.window_hours          # dotted path into the YAML mapping
    controlled_by: external          # external | us
    owner: t_payments
  webhook.dedupe_ttl_hours:
    file: config/webhookingress.yaml
    key: dedupe.ttl_hours
    controlled_by: us
    owner: t_payments
```

`controlled_by: external` means the file records a fact about the world (a partner's policy). The fix agent may never propose changing it.

### 3.4 Other source formats

| File | Shape |
| --- | --- |
| `company/people.yaml` | `{id, name, status: active/departed/leave, left_at, memberships: [{team, since, until}]}` |
| `company/teams.yaml` | `{id, name}` |
| `catalog/services.yaml` | `{id, name, tier: 1..3, owner: team_id, aliases: [], depends_on: [{to, kind: sync/async}], fictional: bool}` |
| `tickets/tickets.jsonl` | `{id, title, body, author, created_at, comments: [{author, body, created_at}]}` |
| `chat/chat.jsonl` | `{id, channel, author, ts, text, thread}` |
| `docs/runbooks/*.md` | Markdown; optional front matter `{authors: [], about: []}` |

### 3.5 Ingestion validation rules (hard errors stop the revision)

1. Every referenced id resolves (people, teams, services, guarantees, assumptions, facts, decisions).
2. Guarantee and assumption ids are globally unique.
3. The `REQUIRES` graph over guarantees is acyclic.
4. The longest `REQUIRES` chain from any guarantee to an assumption is at most 6 edges.
5. Every fact key exists in its file and parses as int, float, or string.
6. Every `relies_on` guarantee of a decision that also appears as a requirement of a guarantee it provides must be consistent: if a provided guarantee requires guarantee X, the providing decision must list X in `relies_on`.
7. `supersedes` targets must have `status: superseded`.
8. Every guarantee has at least one `about` service.

Warnings (recorded on GraphState, shown in UI, do not stop ingestion): an assumption required by no guarantee ("orphan assumption"); an accepted decision with no active accountable person ("orphaned decision"); a guarantee with no accepted provider.

---

## 4. FalkorDB graph schema

Graph name: `premise_kestrel`. Tests use `premise_test_<uuid>` graphs and delete them (one isolated graph per test run).

Every domain node also carries the secondary label `:Entity` with `id` and `search_text` (id, name or title, aliases, statement) for one fulltext index used by entity resolution.

### 4.1 Node labels

| Label | Properties | Created from |
| --- | --- | --- |
| Person | id, name, status (active, departed, leave), left_at (epoch ms or null) | people.yaml |
| Team | id, name | teams.yaml |
| Service | id, name, tier (1 to 3), aliases (list), fictional (bool) | services.yaml |
| Decision | id, title, status (proposed, accepted, superseded), decided_at | ADR front matter |
| Guarantee | id, statement | ADR `provides` |
| Assumption | id, text, check_kind (predicate, manual), op, rhs_const | ADR `assumptions` |
| Fact | id, file, key, value, value_type (int, float, string), line, controlled_by (us, external) | facts.yaml plus the config file |
| Source | id, kind (adr, config, catalog, people, ticket, chat, doc), path, title, url, commit_sha, ts | every file or record ingested |
| Passage | id, text, start_line, end_line | ADR bodies, runbooks, ticket bodies and comments, chat messages |
| ChangeProposal | id (`pr:<n>`), pr_number, title, head_sha, head_ref, base_ref, same_repo (bool), changed_paths (list), state | poller |
| Assessment | id, verdict (BLOCKED, NEEDS_REVIEW, CLEAR_WITHIN_SCOPE, ERROR), reasons_json, result_json, graph_rev, head_sha, created_at | assessor |
| Action | id, kind (status, comment, fix_pr), idem_key, status (executing, done, failed, skipped), external_url, error, created_at | executor |
| GraphState | id = `state`, rev, main_sha, ingest_state (ingesting, ready, failed), warnings_json, pr_cursor_json | ingestor, poller |

### 4.2 Relationship types

Authored relationships (swept by revision) carry `src` (Source id), `line`, `rev`.

| Type | From to | Extra properties | Meaning |
| --- | --- | --- | --- |
| MEMBER_OF | Person to Team | since, until | until null means current |
| OWNS | Team to Service | | accountable team |
| DEPENDS_ON | Service to Service | kind | consumer to provider |
| ACCOUNTABLE_FOR | Person to Decision | role | author or approver |
| GOVERNS | Decision to Service | | |
| SUPERSEDES | Decision to Decision | | explicit only |
| PROVIDES | Decision to Guarantee | | the decision promises this |
| RELIES_ON | Decision to Guarantee | | the decision's rationale needs this |
| REQUIRES | Guarantee to Guarantee or Assumption | | the only propagation edge |
| ABOUT | Guarantee to Service | | whose behaviour is promised |
| LHS, RHS | Assumption to Fact | | predicate operands |
| ATTESTED | Person to Assumption | on, review_by (epoch ms), evidence | a person vouches for a manual assumption until review_by |
| STATED_IN | Decision, Guarantee, Assumption to Source | | line of the declaration |
| DEFINED_IN | Fact to Source | | line of the key in the config file |
| PART_OF | Passage to Source | | |
| AUTHORED | Person to Source | | |
| MENTIONS | Passage to Entity | method (alias) | deterministic resolver |

Memory relationships (never swept):

| Type | From to | Properties |
| --- | --- | --- |
| CHANGES | ChangeProposal to Fact | from, to, deleted (bool) |
| OF | Assessment to ChangeProposal | |
| FOUND | Assessment to Assumption or Guarantee | role (violated, unevaluable, broken, unknown) |
| FLAGGED | Assessment to Decision | roles (list: promises, relies_on) |
| TOOK | Assessment to Action | |

### 4.3 Schema picture

```
 Person -MEMBER_OF-> Team -OWNS-> Service <-DEPENDS_ON- Service
   |                                 ^   ^
   | ACCOUNTABLE_FOR                 |   | ABOUT
   v                     GOVERNS     |   |
 Decision ---------------------------+   |
   |  |  \__SUPERSEDES__> Decision        |
   |  |                                   |
   |  +--PROVIDES--> Guarantee ----------+
   +--RELIES_ON--->  Guarantee
                       |  REQUIRES (only propagation edge, acyclic, depth <= 6)
                       v
                 Guarantee ... -> Assumption -LHS/RHS-> Fact -DEFINED_IN-> Source (file, line)

 Passage -PART_OF-> Source <-AUTHORED- Person        Passage -MENTIONS-> Entity
 Decision, Guarantee, Assumption -STATED_IN-> Source (file, line)

 ChangeProposal -CHANGES{from,to}-> Fact             (overlay record, main facts untouched)
 Assessment -OF-> ChangeProposal; -FOUND-> Assumption/Guarantee; -FLAGGED-> Decision; -TOOK-> Action
```

### 4.4 Indexes

```
CREATE INDEX FOR (n:Entity) ON (n.id)
CREATE INDEX FOR (n:Decision) ON (n.id)        (and Guarantee, Assumption, Fact, Service, Person, Team, Source, Passage)
CREATE INDEX FOR (n:ChangeProposal) ON (n.id)
CREATE INDEX FOR (n:Assessment) ON (n.id)
CREATE INDEX FOR (n:Action) ON (n.idem_key)
CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.search_text)
CREATE FULLTEXT INDEX FOR (n:Passage) ON (n.text)
```

### 4.5 Revisions and the sweep

Ingestion of revision R:

1. `SET state.ingest_state = 'ingesting'`.
2. MERGE every node by id, `SET` its properties and `seen_rev = R`.
3. MERGE every authored edge, `SET r.rev = R, r.src = ..., r.line = ...`.
4. Delete stale authored edges: `MATCH ()-[r]->() WHERE type(r) IN $authored_types AND r.rev < $R DELETE r`.
5. Nodes with `seen_rev < R` get `retired_rev = R`. They have no authored edges left, so no traversal reaches them; memory edges to them survive for history.
6. Recreate indexes if missing, run validation queries, then `SET state.rev = R, state.main_sha = $sha, state.ingest_state = 'ready'`.

Any failure leaves `ingest_state = 'ingesting'` or `failed`; assessments refuse to run (ERROR) until a later ingestion succeeds. Ingestion is idempotent: rerunning the same sha produces identical counts (test T14).

---

## 5. Reasoning semantics

### 5.1 Assumption evaluation

Every assumption in the evaluation set (5.2) gets exactly one state under an overlay O (PR changes plus optional what if changes) at time `now` (a parameter, so tests and replays are deterministic).

**Predicate assumptions**

- `lv` = overlay value of the LHS fact if the fact is in O (even if the overlay value is null), else the main value.
- `rv` = `rhs_const`, or the RHS fact resolved the same way.
- `holds` = comparison result if both operands are numeric, or both strings with `==`; otherwise `null`.

**Manual assumptions** hold only with a current attestation: an `ATTESTED` edge from a Person whose status is `active`, with `date <= now` and `review_by` null or `>= now`. Otherwise `holds` is null. A manual assumption is never *violated* in the MVP (nothing proves it false), and it is never *assumed* true either.

| holds | Kind | Assumption state |
| --- | --- | --- |
| true | any | holding |
| false | predicate | violated |
| null | predicate | unevaluable (missing fact, deleted key, type mismatch, unknown operator) |
| null | manual | unverified (no attestation, expired, dated in the future, or attester departed or on leave) |

### 5.2 Evaluation set and guarantee rollup

A guarantee is judged on all of its prerequisites, never only on the ones a change touches.

1. **touched** = predicate assumptions whose LHS or RHS fact is in the overlay
2. **affected** = every guarantee with a `REQUIRES*1..6` chain to a touched assumption
3. **siblings** = guarantees provided by the same accepted decisions as an affected guarantee, together with the accepted decisions that rely on them
4. **checked** = affected plus siblings
5. **prerequisites** = every assumption reachable from any checked guarantee, plus touched assumptions: unchanged facts and manual attestations included
6. Evaluate every prerequisite under the overlay, then roll up each checked guarantee
7. **Baseline:** evaluate the same prerequisites with an empty overlay (main). Each affected guarantee carries `baseline` and `status`; a reason whose guarantee status equals its baseline is marked `pre_existing`

Rollup is three valued AND: a guarantee **holds** only if every reachable assumption is holding; it is **broken** if any is violated; otherwise **unknown** (some prerequisite is unevaluable or unverified). The witness chain is the shortest path to a violated assumption if one exists, else to an unknown one.

**Main health** (Brain page) uses the same procedure with checked = all guarantees and an empty overlay. With the sandbox data, G_RATES_FRESH is unknown on main because its attestation expired on 2026-09-30.

### 5.3 Decision impact

An accepted decision is **flagged** with role `promises` if it PROVIDES an affected guarantee that is broken or unknown, and role `relies_on` if it RELIES_ON one. Superseded and proposed decisions are never flagged. Decisions are reported only through these two edges; nothing propagates from a decision onward.

**Checked and not affected:** an accepted, unflagged decision that relies on a sibling guarantee whose full prerequisite set was evaluated under the overlay and **holds**. A sibling that is broken or unknown is listed separately as **checked, with a problem** (it is not caused by this PR, so it never changes the verdict and is never reported as unaffected). Absence from the affected results is never enough.

### 5.4 Criticality

A guarantee's tier = minimum tier over its ABOUT services and the GOVERNS services of its accepted providers and reliers. Tier 1 is most critical.

### 5.5 Exposure

Callers of each ABOUT service via `DEPENDS_ON*1..3`. Reported, never used for the verdict.

### 5.6 Accountability routing

For each flagged decision: active accountable people are the reviewers. If none are active, candidates are active members (membership `until` null, status active, not on leave) of teams that OWN the decision's governed services, ranked by count of distinct sources they authored in the last 180 days whose passages MENTION those services, then by id ascending. Top 3. No candidate means the decision is **unroutable**.

### 5.7 Verdict policy

| Order | Rule | Verdict | Reason code |
| --- | --- | --- | --- |
| 0 | FalkorDB unreachable, `ingest_state != ready`, or an exception | ERROR | `R_UNAVAILABLE` |
| 1 | Any broken guarantee with tier 1 | BLOCKED | `R_BROKEN_T1` |
| 2 | Any broken guarantee with tier 2 or 3 | NEEDS_REVIEW | `R_BROKEN_LOW_TIER` |
| 3 | Any unknown guarantee (an unevaluable or unverified prerequisite) | NEEDS_REVIEW | `R_UNKNOWN` |
| 4 | A violated or unevaluable assumption that no guarantee requires | NEEDS_REVIEW | `R_ORPHAN_ASSUMPTION` |
| 5 | PR touches model files | NEEDS_REVIEW | `R_MODEL_CHANGE` |
| 6 | A flagged decision is unroutable | NEEDS_REVIEW | `R_UNROUTABLE` |
| 7 | A broken or unknown guarantee has no accepted provider | NEEDS_REVIEW | `R_NO_PROVIDER` |
| 8 | No tracked fact value changed | CLEAR_WITHIN_SCOPE | `R_NO_TRACKED_FACTS` |
| 9 | Otherwise | CLEAR_WITHIN_SCOPE | `R_ALL_HOLD` |

Rules 1 to 3 apply to the **status under the overlay** of each affected guarantee, judged on its full prerequisite set. The verdict is the most severe rule that fires; **all** firing reasons are listed. A BLOCKED assessment can carry review reasons too. Missing data can raise severity but can never lower it. A reason marked `pre_existing` (the guarantee was already broken or unknown on main) keeps its severity: a PR that changes an input of a guarantee that is already broken or unverifiable gets that verdict, with the pre-existing flag shown so the author knows it was not caused by them.

| Verdict | Commit status state | Description (max 140 chars) |
| --- | --- | --- |
| BLOCKED | failure | `Blocked: breaks G_DEDUPE and 3 more guarantees via A_RETRY_WINDOW` |
| NEEDS_REVIEW | failure | `Needs review: G_DEDUPE cannot be evaluated (webhook.dedupe_ttl_hours missing)` |
| CLEAR_WITHIN_SCOPE | success | `Clear: 1 assumption checked, all hold` |
| ERROR | error | `Assessment unavailable: graph not ready` |

NEEDS_REVIEW maps to `failure`, not `pending`, because `pending` means "still running" in GitHub and would never resolve. Repo admins can bypass branch protection; optional item O2 adds a recorded human acknowledgement.

---

## 6. Cypher queries (final)

All queries live as `.cypher` files in `premise/graph/queries/` so the README links them verbatim. Read queries run through `GRAPH.RO_QUERY`. Parameters only; nothing an LLM writes is ever concatenated into Cypher.

### E1. Evaluate assumptions under an overlay (`evaluate_assumptions.cypher`)

`$ids`: the prerequisite set from 5.2. `$overlay`: list of `{fact, to}` maps (a deleted key has `to: null`). `$now`: epoch ms.

```cypher
// E1. Evaluate assumptions under an overlay of proposed fact values.
// Predicate assumptions: compare operands; a fact present in the overlay uses the overlay value even when it is null
// (a deleted key), so missing data can never fall back to the old value.
// Manual assumptions: hold only with a current attestation by an active person; otherwise holds is null (unverified).
UNWIND $ids AS aid
MATCH (a:Assumption {id: aid})
OPTIONAL MATCH (a)-[:LHS]->(l:Fact)
OPTIONAL MATCH (a)-[:RHS]->(r:Fact)
OPTIONAL MATCH (p:Person)-[at:ATTESTED]->(a)
WITH a, l, r,
     [x IN collect({person: p.id, status: p.status, on: at.on, review_by: at.review_by}) WHERE x.person IS NOT NULL] AS atts
WITH a, l, r, atts,
     CASE WHEN l IS NULL THEN null
          WHEN any(o IN $overlay WHERE o.fact = l.id) THEN head([o IN $overlay WHERE o.fact = l.id | o.to])
          ELSE l.value END AS lv,
     CASE WHEN r IS NULL THEN a.rhs_const
          WHEN any(o IN $overlay WHERE o.fact = r.id) THEN head([o IN $overlay WHERE o.fact = r.id | o.to])
          ELSE r.value END AS rv
WITH a, l, r, atts, lv, rv,
     ((typeOf(lv) IN ['Integer', 'Float'] AND typeOf(rv) IN ['Integer', 'Float'])
      OR (typeOf(lv) = 'String' AND typeOf(rv) = 'String' AND a.op = '==')) AS comparable,
     any(x IN atts WHERE x.status = 'active' AND x.on <= $now
                     AND (x.review_by IS NULL OR x.review_by >= $now)) AS attested
RETURN a.id AS id, a.check_kind AS kind, a.text AS text,
       l.id AS lhs_fact, lv, a.op AS op, r.id AS rhs_fact, rv, atts,
       CASE WHEN a.check_kind = 'manual' THEN (CASE WHEN attested THEN true ELSE null END)
            WHEN NOT comparable THEN null
            WHEN a.op = '<=' THEN lv <= rv
            WHEN a.op = '<'  THEN lv <  rv
            WHEN a.op = '>=' THEN lv >= rv
            WHEN a.op = '>'  THEN lv >  rv
            WHEN a.op = '==' THEN lv =  rv
            ELSE null END AS holds
ORDER BY id
```

The `any(...)` check, not `coalesce`, is deliberate: a deleted key must evaluate as null, not fall back to the main value (test T2).

### Q1. Evaluation set (`touched_assumptions.cypher`, `guarantee_assumption_pairs.cypher`, `siblings.cypher`)

```cypher
// Assumptions whose predicate reads at least one of the given facts.
MATCH (a:Assumption)-[:LHS|RHS]->(f:Fact)
WHERE f.id IN $facts
RETURN DISTINCT a.id AS id
ORDER BY id
```

```cypher
// Every (guarantee, assumption) pair joined by a REQUIRES chain of 1 to 6 hops.
// Used upward (ancestors of touched assumptions) and downward (closure of checked guarantees).
MATCH (g:Guarantee)-[:REQUIRES*1..6]->(a:Assumption)
WHERE ($assumptions IS NULL OR a.id IN $assumptions)
  AND ($guarantees IS NULL OR g.id IN $guarantees)
RETURN DISTINCT g.id AS guarantee, a.id AS assumption
ORDER BY guarantee, assumption
```

The pairs query runs twice: upward with `$assumptions = touched` (affected guarantees and orphan detection), then downward with `$guarantees = checked` (every prerequisite of every checked guarantee).

```cypher
// Guarantees provided by the same accepted decisions as the affected ones, but not affected themselves,
// together with the accepted decisions that rely on them. These are evaluated, not assumed healthy.
MATCH (pd:Decision {status: 'accepted'})-[:PROVIDES]->(g:Guarantee)
WHERE g.id IN $affected
MATCH (pd)-[:PROVIDES]->(sib:Guarantee)
WHERE NOT sib.id IN $affected
MATCH (rd:Decision {status: 'accepted'})-[:RELIES_ON]->(sib)
RETURN DISTINCT sib.id AS guarantee, rd.id AS decision, pd.id AS provider
ORDER BY decision, guarantee
```

### Q2. Three valued rollup (`rollup_guarantees.cypher`)

```cypher
// Q2a. Three valued AND over every prerequisite of each guarantee.
// $violated and $unknown hold assumption ids from E1 (unknown = unevaluable or unverified).
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

### Q2b. Impact of non holding guarantees (`guarantee_impact.cypher`)

```cypher
// Q2b. For guarantees that are broken or unknown: accepted decisions that promise or rely on them,
// the services they are about, criticality tiers, and callers exposed through DEPENDS_ON (up to 3 hops).
UNWIND $guarantees AS gid
MATCH (g:Guarantee {id: gid})
OPTIONAL MATCH (pd:Decision {status: 'accepted'})-[:PROVIDES]->(g)
OPTIONAL MATCH (rd:Decision {status: 'accepted'})-[:RELIES_ON]->(g)
OPTIONAL MATCH (g)-[:ABOUT]->(s:Service)
OPTIONAL MATCH (pd)-[:GOVERNS]->(ps:Service)
OPTIONAL MATCH (rd)-[:GOVERNS]->(rs:Service)
OPTIONAL MATCH (caller:Service)-[:DEPENDS_ON*1..3]->(s)
RETURN g.id AS guarantee,
       collect(DISTINCT pd.id) AS promised_by,
       collect(DISTINCT rd.id) AS relied_on_by,
       collect(DISTINCT s.id) AS about,
       [t IN collect(DISTINCT s.tier) + collect(DISTINCT ps.tier) + collect(DISTINCT rs.tier) WHERE t IS NOT NULL] AS tiers,
       collect(DISTINCT caller.id) AS exposed_callers
ORDER BY guarantee
```

Python takes `min(tiers)` as the guarantee's tier (validation rule 8 guarantees at least one ABOUT service) and adds `R_NO_PROVIDER` when `promised_by` is empty. Together Q1, Q2 and Q2b reach up to 6 hops to an assumption, 1 to each decision, 1 to governed services, and 3 more to callers.

### Q3. Accountability routing

```cypher
MATCH (d:Decision {id: $decision_id})
OPTIONAL MATCH (p:Person)-[:ACCOUNTABLE_FOR]->(d)
WITH d, collect(p) AS acc
WITH d,
     [x IN acc WHERE x.status = 'active' | x.id] AS active_accountable,
     [x IN acc WHERE x.status <> 'active' | x.id] AS gone
OPTIONAL MATCH (d)-[:GOVERNS]->(s:Service)<-[:OWNS]-(t:Team)<-[m:MEMBER_OF]-(c:Person)
WHERE c.status = 'active' AND m.until IS NULL
OPTIONAL MATCH (c)-[:AUTHORED]->(src:Source)<-[:PART_OF]-(:Passage)-[:MENTIONS]->(s)
WHERE src.ts >= $since_ms
WITH d, active_accountable, gone, c, t, count(DISTINCT src) AS evidence
ORDER BY evidence DESC, c.id ASC
RETURN active_accountable, gone,
       [x IN collect({person: c.id, team: t.id, evidence: evidence}) WHERE x.person IS NOT NULL] AS candidates
```

Python keeps the first 3 candidates. Routing uses candidates only when `active_accountable` is empty.

### H1. Guarantee coverage (Brain page)

```cypher
MATCH (g:Guarantee)
OPTIONAL MATCH (g)-[:REQUIRES*1..6]->(a:Assumption)
RETURN g.id AS guarantee, g.statement AS statement,
       count(DISTINCT a) AS assumptions,
       count(DISTINCT CASE WHEN a.check_kind = 'manual' THEN a END) AS unverified
ORDER BY guarantee
```

Main health = E1 with empty overlay and empty scope, then Q2 over its failing rows; guarantees absent from Q2 hold.

### H2. Orphaned decisions (Track 3 audit)

```cypher
MATCH (d:Decision {status: 'accepted'})-[:GOVERNS]->(s:Service)
OPTIONAL MATCH (p:Person)-[:ACCOUNTABLE_FOR]->(d)
WITH d, collect(DISTINCT s.id) AS services, min(s.tier) AS tier, collect(DISTINCT p) AS acc
WHERE none(x IN acc WHERE x.status = 'active')
RETURN d.id AS decision, d.title AS title, services, tier, [x IN acc | x.id] AS departed
ORDER BY tier, decision
```

### A1. Load bearing guarantees (algorithm as a tool)

```cypher
CALL algo.pageRank('Guarantee', 'REQUIRES') YIELD node, score
RETURN node.id AS guarantee, score
ORDER BY score DESC
LIMIT $limit
```

A guarantee required by many others scores highest. Used for ordering on the Brain page and as an Analyst tool, never in the verdict.

### Supporting read queries

| Name | Purpose | Core pattern |
| --- | --- | --- |
| R1 resolve | name to ids | `CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node, score` |
| L1 lineage | a decision's full reasoning | PROVIDES and RELIES_ON guarantees, their `REQUIRES*1..6` trees to assumptions and facts, SUPERSEDES both ways, STATED_IN lines, accountable people |
| W1 who_knows | expertise on a service | owning team members plus Q3's authored evidence count |
| S1 search_evidence | text search with sources | `CALL db.idx.fulltext.queryNodes('Passage', $q)` then PART_OF Source and MENTIONS |
| M1 recall | past assessments for an entity | `(as:Assessment)-[:FOUND or FLAGGED]->(n {id: $id})`, newest first |
| X1 explain_connection (optional) | why two things relate | `shortestPath` with both endpoints bound |

---

## 7. Agent workflow

### 7.1 PR assessment pipeline (deterministic spine)

```
 PR head sha changed
   |
   v
 [1] Guard: GraphState.ingest_state == ready? -- no --> status error, stop
   |
   v
 [2] Status "pending: assessing" on head sha
   |
   v
 [3] Intake (git): merge_base(main, head); changed paths = diff(merge_base..head)
     for each changed path hosting a registered fact: read value at head
     overlay = facts whose value differs from main (deleted key -> to: null)
     model_change = any changed path in adr/, facts.yaml, catalog/, company/
     write ChangeProposal + CHANGES edges (replace previous CHANGES for this PR)
   |
   v
 [4] Q1 -> touched assumptions, affected guarantees, siblings, full prerequisite set
 [5] E1 over every prerequisite (overlay) and again on main (baseline)
 [6] Q2 rollup -> broken / unknown / holds per checked guarantee; Q2b impact for non holding ones
     siblings that hold -> checked and not affected; siblings that do not -> checked, with a problem
 [7] Q3 per flagged decision -> reviewers or candidates
 [8] Policy -> verdict + reasons (pre_existing marked against the baseline)
   |
   v
 [9] Fix agent (only if a violated predicate assumption exists)
   |
   v
 [10] Render: Mermaid chain + tables + permalinks + verified fixes + LLM summary (id checked)
 [11] Write Assessment (id = hash(pr, head_sha, graph_rev)), FOUND, FLAGGED edges
 [12] Staleness check: head sha and GraphState.rev unchanged? -- no --> abort actions, requeue
 [13] Execute actions with idempotency keys; write Action nodes; TOOK edges
```

### 7.2 Fix agent: LLM proposes, graph verifies, policy disposes

**Goal:** find changes to facts controlled by us that make every assumption in scope hold.

**Tools (function calls, all graph backed):**

| Tool | Input | Output |
| --- | --- | --- |
| `violation_context` | none (bound to current assessment) | violated assumptions with predicates, current and proposed values, `controlled_by` of each operand, guarantees they break |
| `assumptions_on_fact` | fact id | every predicate assumption using that fact, with current evaluation |
| `test_fix` | `changes: {fact_id: value}` | The full evaluation of 5.2 (Q1, E1, Q2) with overlay = PR overlay plus changes. `all_hold` is true only if every affected guarantee holds on **all** its prerequisites (unchanged facts and attestations included) and every touched assumption holds. Also returns violated, unevaluable, unverified, and guarantee statuses |

**Loop:** at most 8 tool calls, then a final structured answer `{fixes: [{changes, rationale}]}`. Request settings follow section 7.6 (no sampling parameters, `tool_choice: auto`).

**Controller rules (enforced in code, not prompt):**

1. A fix is accepted only if the identical `changes` map was passed to `test_fix` in this session and returned `all_hold = true`.
2. Only facts with `controlled_by: us`; numeric values only; at most 3 facts per fix.
3. Never propose reverting an external fact (the PR records reality).
4. At most 3 accepted fixes, ranked by number of facts changed, then total relative change.
5. A fix that removes every violation but leaves an affected guarantee unknown (for example an unverified manual prerequisite) is reported as **partial**, never verified, and never opened as a fix PR.

**Deterministic repair (always runs, also the fallback):**

1. Group violated assumptions into clusters: two violations share a cluster if their fact sets overlap (directly or through assumptions on the same facts).
2. Per cluster, breadth first over candidate changes, depth at most 2. For each violated predicate in the prerequisite set (including violations on unchanged facts), generate "set the controllable side equal to the bound" (for strict operators on ints, bound plus or minus 1). Evaluate every candidate with the full `test_fix`. A candidate is acceptable for its cluster when the cluster's violations are gone and nothing new is violated, unevaluable, or unverified; it is **verified** only if `all_hold` is true. If new violations appear, extend the candidate once by repairing them the same way.
3. Combine the best verified fix of each cluster into one combined fix and verify it once more with `test_fix` over all PR facts. Offer per cluster fixes and the combined fix.
4. Budget: at most 16 `test_fix` evaluations per assessment.
5. Rejected candidates are kept with the assumptions they break, because showing a rejected plausible fix is part of the explanation.

**Outcome in the demo scenario:** candidate `{webhook.dedupe_ttl_hours: 72}` is rejected (breaks `A_REDIS_TTL`: 72 <= 48 is false); `{webhook.dedupe_ttl_hours: 72, redis.max_ttl_hours: 72}` is verified.

**Fix PR execution (policy):** open a fix PR only if a verified, non revert fix exists, the PR is from the same repo, and auto fix is enabled. The fix PR is **stacked**: its base is the original PR's head branch, so merging it updates the original PR, which is then reassessed. Values are edited by replacing the value on the exact line recorded for the fact (no YAML re dump, comments preserved).

### 7.3 PR comment

One comment per PR, created once and edited on every reassessment, identified by `<!-- premise:pr:<n> -->`. Posted with the issue comments API (no review API, which avoids the restriction on reviewing your own PR). Sections:

1. Verdict line and reason codes.
2. **What changed:** fact, old to new, permalink to the line.
3. **What broke:** assumption, predicate with values, permalinks to both operand lines and to the assumption declaration.
4. **How far it reaches:** Mermaid flowchart from assumption through the guarantee chain, decisions attached with dotted edges labelled "promises" or "relies on"; a table of guarantee, status, tier, promised by, relied on by, services, exposed callers.
5. **Checked and not affected:** Q2b rows ("ADR-016 relies on G_ACK_FAST, also provided by ADR-007; it still holds").
6. **Who should review:** accountable people by name in plain text; departed people noted; candidates with their evidence count. Never `@` mentions or assignees for synthetic people.
7. **Verified fixes** and **rejected fixes** with the failing assumption.
8. Footer: graph revision, head sha, assessment link, hidden marker.

A 3 sentence LLM summary may lead the comment. Every id like token in it (`ADR-\d{3}`, `G_[A-Z_]+`, `A_[A-Z_]+`, service ids, person ids, fact ids) must appear in the assessment result, or the summary is dropped. The rest of the comment is a deterministic template.

### 7.4 Analyst Q&A and MCP (Track 3)

**Read tools** (shared by the web Analyst and the MCP server): `resolve`, `decision_lineage`, `guarantee_health`, `who_knows`, `search_evidence`, `orphaned_decisions`, `load_bearing_guarantees`, `impact_if_broken` (Q2 with one hypothetical assumption), `recall`.

**Web Analyst loop:** at most 6 tool calls (request settings per section 7.6), output `{outcome, answer_markdown, cited_ids}` where outcome is one of `answered_with_path`, `answered_from_memory`, `not_in_graph`, `unknown_entity`. Verification: every id in the answer must appear in tool results; citations are rendered by the server from Source permalinks, never written by the model. On failure, the answer falls back to a table built from the last tool rows. "Not in the graph" is never phrased as "nothing is affected."

**MCP server:** official Python SDK, stdio transport, read only FalkorDB connection, the same tool functions. The MCP client's own model does the reasoning, so it works even when Premise's LLM key is absent.

### 7.5 LLM boundaries

| LLM may | LLM may not |
| --- | --- |
| propose fixes, call tools, write rationale | decide a verdict or skip a rule |
| write a summary that passes id verification | write Cypher, choose actions, name people not in rows |
| answer questions from tool rows | treat PR text, tickets, or chat as instructions (they are passed as quoted untrusted data) |

### 7.6 LLM API configuration (Claude Sonnet 5.5, verified against Anthropic's docs on Oct 16)

| Setting | Value | Why |
| --- | --- | --- |
| model | `claude-sonnet-5-5` (env `LLM_MODEL`) | current Sonnet model ID |
| `temperature`, `top_p`, `top_k` | **not sent** | a non-default value returns 400 on this model |
| `tool_choice` | omitted (`auto`) | `any` and `tool` return 400; tell the model in the prompt when to call a tool; use strict tool use or structured outputs for schema valid arguments |
| assistant prefill | never | returns 400 |
| `thinking` | omitted (adaptive, the default) | `{"type": "disabled"}` returns 400; if thinking must be minimal, send `{"type": "between_tools"}` at `high` effort or below |
| `output_config.effort` | `"medium"` for the fix agent and Analyst loops | the docs recommend starting multistep tool use at medium |
| `max_tokens` | 16000 | thinking counts toward it |
| conversation | append only; pass thinking blocks back unchanged in tool loops | editing earlier turns can make a replayed thinking block return 400 |
| `stop_reason: "refusal"` | handled: fall back to deterministic output | documented response for declined requests |

**Reproducibility without temperature:** the LLM never decides a verdict or which fixes are valid; demo runs replay from a disk cache keyed by the request hash; the deterministic repair search and the row based comment template produce the same output with the LLM switched off. A test asserts that no request built by `agent/llm.py` contains a sampling parameter.

---

## 8. GitHub integration

### 8.1 Setup

- `kestrel-platform`: public repo, default branch `main`, branch protection on `main` requiring status check `premise/decisions` (required checks accept commit statuses), admins may bypass for demo resets.
- Fine grained token scoped to `kestrel-platform` only: Contents read and write (fix branch and file edit), Pull requests read and write, Issues read and write (comments), Commit statuses read and write, Metadata read.
- Scenario branches pushed in advance: `scenario/s1-retry-72`, `scenario/s2-email-decoy`, `scenario/s3-ttl-deleted`, `scenario/s5-charge-timeout`, `scenario/s6-ad-cache`, `scenario/s7-adr-edit`, `scenario/s8-readme`, `scenario/s10-cart-ttl`.

### 8.2 Reading and writing

| Operation | Mechanism |
| --- | --- |
| Main state | `git fetch origin main` into a local clone; worktree at the sha |
| PR content | `git fetch origin pull/<n>/head`; `git merge-base`; `git diff --name-only`; `git show <sha>:<path>` (works for fork PRs too) |
| Open PRs and head shas | `GET /repos/{o}/{r}/pulls?state=open` every 15 s with ETag |
| Commit status | `POST /repos/{o}/{r}/statuses/{sha}` with context `premise/decisions` and `target_url` to the assessment page |
| Comment upsert | list issue comments, find marker, `PATCH` or `POST` |
| Fix PR | create ref `refs/heads/premise/fix-<n>-<hash8>` at the PR head sha; `PUT contents` for each edited file; `POST pulls` with base = PR head ref |

### 8.3 Idempotency, staleness, reconciliation

| Action | Idempotency key | Reconciliation |
| --- | --- | --- |
| status | `status:<pr>:<head_sha>:<verdict>` | statuses are last write wins; re post is safe |
| comment | `comment:<pr>` | search comments for the marker |
| fix_pr | `fix:<pr>:<head_sha>:<fix_hash>` | list PRs whose head ref is the deterministic branch name |

Before calling GitHub, the Action node is written with status `executing`. On startup, `premise reconcile` checks each `executing` action against GitHub and marks it `done` or retries once. Before executing any action, the head sha and graph revision are reread; if either changed, actions are skipped and the PR is requeued. No exactly once claim: one executor plus reconciliation.

---

## 9. Technology stack

| Layer | Choice | Reason | Risk and mitigation |
| --- | --- | --- | --- |
| Graph | FalkorDB module **v4.18.3** (verified Oct 16; every construct in section 15 passed). Docker image tag pinned to the matching 4.18 release; local development and tests use the same module from the `falkordblite` wheel run as a real server | Required; Browser for debugging and video | the Docker tag name still needs checking on Docker Hub |
| Language | Python 3.12, managed with `uv` | Official client and SDKs; fastest with AI coding tools | none |
| API and UI | FastAPI, uvicorn, Jinja2 templates, Mermaid from a pinned CDN version | No build step; the same Mermaid text serves the UI and PR comments | modest polish; FalkorDB Browser carries visuals in the video |
| Models | pydantic v2 | Typed tool arguments and the AssessmentResult contract | none |
| YAML | PyYAML (compose API for line numbers) | Line numbers without another dependency | test line accuracy (T15) |
| HTTP | httpx (with `MockTransport` in tests) | GitHub REST, testable offline | rate limits: ETag polling, low volume |
| Git | git CLI in the container | Fork safe PR reads, exact shas for permalinks | container needs git and a token for fetch |
| LLM | Anthropic Messages API via the official `anthropic` SDK, default model `claude-sonnet-5-5`, set by `LLM_MODEL`; request rules in section 7.6 | Tool use for the fix agent and Analyst | one adapter file `agent/llm.py` with two functions (`tool_loop`, `structured`); switching providers touches only that file; no sampling parameters ever |
| MCP | official `mcp` Python SDK, stdio | Track 1 focus item | test with MCP Inspector before Claude Desktop |
| Tests | pytest against a real FalkorDB server (`FALKORDB_PORT`, or the fixture starts one) | Graph semantics must be tested on the real engine | 47 tests run in about 5 seconds |
| Packaging | Docker Compose: `falkordb`, `app` | One command setup for judges | none |

**Rejected:** LangChain and LangGraph (abstraction without benefit at a dozen tools), GraphRAG SDK, Graphiti, Cognee (they own the schema), text to Cypher including QueryWeaver (unverifiable on stage), Next.js and force graph canvases (time sink), embeddings in the MVP (not needed for the core claim), any queue or second database, Slack and Discord, webhooks (need a public endpoint; polling is enough).

### 9.1 Code layout

```
premise/
  config.py                 env: FALKORDB_URL, GRAPH_NAME, GITHUB_TOKEN, SANDBOX_REPO,
                            SANDBOX_CLONE_DIR, ANTHROPIC_API_KEY, LLM_MODEL, PUBLIC_BASE_URL,
                            POLL_SECONDS=15, AUTO_FIX_PR=true, SINCE_DAYS=180
  graph/
    client.py               connection, ro/rw helpers, graph selection
    schema.py               index creation, authored relationship type list
    queries/*.cypher        E1, Q2, Q2b, Q3, H1, H2, A1, R1, L1, W1, S1, M1, sweep
  ingest/
    parse_company.py  parse_catalog.py  parse_facts.py  parse_adr.py  parse_text.py
    validate.py  load.py  mentions.py  run.py
  reasoning/
    evaluate.py   impact.py   route.py   policy.py   repair.py   models.py (AssessmentResult)
  agent/
    llm.py  fix_agent.py  analyst.py  verify.py  render.py (comment, mermaid)
  github/
    gitrepo.py  api.py  poller.py  actions.py  reconcile.py
  web/
    app.py  templates/brain.html  assessment.html  entity.html
  mcp_server.py
  cli.py
tests/
  fixtures/mini_company/    hermetic copy of the sandbox model used by unit tests
  fixtures/expected.yaml    scenario ground truth
  test_*.py
docker-compose.yml
README.md
```

### 9.2 The AssessmentResult contract (lets two people work in parallel)

```
AssessmentResult
  pr, head_sha, graph_rev, verdict, reasons: [{code, ids, detail}]
  changed_facts: [{fact, from, to, deleted, controlled_by, file, line, permalink}]
  assumptions:   [{id, state, lhs_fact, lv, op, rhs_fact, rv, permalink}]
  guarantees:    [{id, status, chain, tier, promised_by, relied_on_by, about, exposed_callers}]
  decisions:     [{id, roles, active_accountable, departed, candidates: [{person, team, evidence}], permalink}]
  not_affected:  [{decision, via_guarantee, sibling_of}]
  fixes:         [{changes, status: verified|rejected, failed_assumptions, origin: llm|repair, rationale}]
  mermaid, created_at
```

`premise assess --pr N --json` prints exactly this; tests and the renderer consume it.

---

## 10. Features

### 10.1 Mandatory (about 32 hours)

| ID | Feature | Acceptance criterion |
| --- | --- | --- |
| F1 | Sandbox company repo with the decision model as code (section 12) | All validation rules pass; scenario branches pushed |
| F2 | Deterministic ingestion with provenance, validation, revisions, sweep | T9, T14, T15 pass |
| F3 | Assumption evaluator with overlay and what if (E1) | T1, T2, T3 pass |
| F4 | Guarantee propagation, decision impact, precision list, exposure (Q2, Q2b) | T4 to T8 pass |
| F5 | Accountability routing (Q3) | T10 passes |
| F6 | Verdict policy with reason codes and ERROR | T11, T16 pass |
| F7 | PR intake via git and polling; main ingestion trigger; reassess open PRs on new revision | scenario S1 assessed from a real PR |
| F8 | GitHub actions: commit status, upserted comment with Mermaid and permalinks, Action nodes, idempotency, staleness, reconcile | T17, T18 pass; real PR goes red with comment |
| F9 | Fix agent with controller rules and deterministic repair; stacked fix PR | T12 passes; merging the fix PR turns S1 green |
| F10 | Analyst Q&A with verification and four outcomes; MCP server with read tools | T19 passes; three demo questions answered in Claude Desktop |
| F11 | Web UI: Brain page (guarantee board ordered by PageRank, coverage, orphaned decisions, recent assessments, ask box), assessment page, entity page | commit status link opens the assessment page |
| F12 | Lexical gap evidence (fulltext over decision passages vs graph impact) | T13 passes; numbers shown on the assessment page |
| F13 | Test suite T1 to T19 and scenario runner `premise scenarios` | all green in CI or locally |
| F14 | README, Compose, AI disclosure, demo video | fresh clone setup works |

### 10.2 Optional, in priority order

| ID | Feature | Hours | Why |
| --- | --- | --- | --- |
| O1 | RAG baseline: fulltext top k passages plus LLM "which decisions are affected?", scored on every scenario against ground truth; embeddings variant via `fastembed` if time | 2.5 | Turns the core claim into measured numbers |
| O2 | `/premise ack <reason>` comment command: a collaborator acknowledges NEEDS_REVIEW, recorded as a Verdict node, status becomes success | 1.5 | Human decision memory; makes NEEDS_REVIEW resolvable |
| O3 | Live deployment of Compose on a small VM; `target_url` points there | 2.5 | Preferred by the rules |
| O4 | Issue on main when a broken guarantee reaches main (bypass or direct push) | 1 | Currency story on main |
| O5 | Prose evidence: tickets and chat judged against assumptions (graph scoped candidates, quote verified), marked contested, surfaced as NEEDS_REVIEW issues | 4 | Strengthens Track 3 knowledge from tickets and chats |
| O6 | Waivers with expiry on a specific violated assumption | 1.5 | Explicit, time bounded risk acceptance |
| O7 | `explain_connection` via shortest path; departure trigger (people.yaml status change on main posts an orphaned decisions issue) | 1.5 | Cheap extra tools |
| O8 | Blog post | 2 | Side prize |

### 10.3 Not building

LLM extraction of assumptions, customer commitments, Kubernetes public tenant, Slack or Discord, Jira, webhooks, authentication, multiple tenants in the UI, evaluating edited ADRs before merge, OR semantics in guarantees, any weighted risk score.

---

## 11. Demo script (3 minutes)

| Time | Screen | Action and line | Proves |
| --- | --- | --- | --- |
| 0:00 to 0:15 | `adr/ADR-007.md` | "Decisions promise guarantees. Guarantees need assumptions. Premise makes both checkable." Show `G_DEDUPE` and `A_RETRY_WINDOW` | the model |
| 0:15 to 0:30 | GitHub | Open PR from `scenario/s1-retry-72`: "Record Paylane's new 72 hour retry policy". Tests green | real input |
| 0:30 to 1:15 | PR | `premise/decisions` fails. Comment: 72 > 24 with permalinks; Mermaid chain `A_RETRY_WINDOW -> G_DEDUPE -> G_CHARGE_ONCE -> G_REFUND_MATCH, G_LEDGER_CONSISTENT`; ADR-012 relies on G_DEDUPE and never mentions retries; tier 1 paymentservice; checked and not affected: ADR-016; ADR-012's accountable people left, routed to Jun with evidence | multihop, precision, provenance, accountability, real gate |
| 1:15 to 1:50 | PR, fix PR | Rejected fix: TTL 72 breaks A_REDIS_TTL (Redis caps at 48). Verified fix: TTL 72 and Redis max 72. Fix PR opened against the PR branch; merge it; original PR reassessed; green | agent decides and acts, graph verified |
| 1:50 to 2:05 | Second PR | `scenario/s2-email-decoy` raises email retries: green, "A_EMAIL_BUDGET holds (8 <= 10)" | restraint |
| 2:05 to 2:20 | Assessment page | Lexical gap panel: fulltext for the PR's terms finds ADR-007 and ADR-016 (a false lead); the graph finds ADR-012, ADR-015, ADR-018 and excludes ADR-016. If O1 shipped, one line of measured baseline numbers | the graph is load bearing |
| 2:20 to 2:50 | Claude Desktop with the Premise MCP server | "Which guarantees are load bearing, and which rest on unverified assumptions?" then "Why does paymentservice skip idempotency, and who owns that decision now?" | Track 3 answers with sources; MCP tool selection |
| 2:50 to 3:00 | Title | "Premise: every change checked against the guarantees your decisions depend on." Tracks and repo | close |

Rehearsal rules: reset with `premise reset --demo` (closes Premise fix PRs and deletes their branches, force resets every scenario branch to the commit recorded in `expected.yaml`, deletes Premise comments on scenario PRs, clears Assessment and Action nodes, reingests main); warm the LLM by running S1 once; record a full fallback take on Saturday night.

---

## 12. Synthetic dataset (kestrel-platform)

All names are fictional. Service topology follows Google's Online Boutique (Apache 2.0) plus two fictional services, labelled `fictional: true`. Verify the Online Boutique call edges against its architecture diagram before seeding.

### 12.1 Teams, people, services

| Team | Owns |
| --- | --- |
| t_payments | paymentservice, webhookingress, refundworker |
| t_storefront | frontend, checkoutservice, cartservice, recommendationservice, adservice |
| t_platform | productcatalogservice, currencyservice, shippingservice, emailservice |

| Person | Team | Status | Note |
| --- | --- | --- | --- |
| p_anika | t_payments | active | author ADR-007, ADR-015; authored 2 recent tickets mentioning paymentservice |
| p_jun | t_payments | active | authored 6 recent tickets mentioning paymentservice |
| p_marco | t_payments | departed 2026-08-14 | author ADR-012 |
| p_lena | t_payments | departed 2026-05-30 | approver ADR-012 |
| p_dev | t_payments | leave | must never be routed |
| p_ravi | t_platform | active | author ADR-018 |
| p_sofia | t_platform | active | author ADR-011 |
| p_omar | t_storefront | active | author ADR-009 |
| p_kim | t_storefront | active | author ADR-020 |
| p_tess | t_platform | active | t_storefront membership ended 2026-07-01 |

| Service | Tier | Depends on |
| --- | --- | --- |
| frontend | 1 | checkoutservice, cartservice, productcatalogservice, currencyservice, shippingservice, recommendationservice, adservice |
| checkoutservice | 1 | cartservice, productcatalogservice, currencyservice, shippingservice, paymentservice, emailservice |
| paymentservice | 1 | |
| cartservice | 1 | |
| webhookingress (fictional) | 1 | paymentservice (async) |
| refundworker (fictional) | 2 | paymentservice |
| productcatalogservice | 2 | |
| currencyservice | 2 | |
| shippingservice | 2 | |
| recommendationservice | 3 | productcatalogservice |
| emailservice | 3 | |
| adservice | 3 | |

### 12.2 Facts

| Fact | File | Value | Controlled by |
| --- | --- | --- | --- |
| paylane.retry_window_hours | config/partners/paylane.yaml | 24 | external |
| paylane.delivery_timeout_ms | config/partners/paylane.yaml | 5000 | external |
| webhook.dedupe_ttl_hours | config/webhookingress.yaml | 24 | us |
| webhook.ack_timeout_ms | config/webhookingress.yaml | 2000 | us |
| redis.max_ttl_hours | config/platform/redis.yaml | 48 | us |
| paymentservice.charge_timeout_ms | config/paymentservice.yaml | 800 | us |
| checkoutservice.payment_timeout_ms | config/checkoutservice.yaml | 1000 | us |
| emailservice.retry_max_attempts | config/emailservice.yaml | 5 | us |
| emailprovider.max_retries | config/partners/emailprovider.yaml | 10 | external |
| currency.cache_ttl_minutes | config/currencyservice.yaml | 30 | us |
| adservice.cache_ttl_seconds | config/adservice.yaml | 120 | us |
| cartservice.session_ttl_hours | config/cartservice.yaml | 72 | us |

### 12.3 Assumptions

| Assumption | Check | Declared in |
| --- | --- | --- |
| A_RETRY_WINDOW | paylane.retry_window_hours <= webhook.dedupe_ttl_hours | ADR-007 |
| A_REDIS_TTL | webhook.dedupe_ttl_hours <= redis.max_ttl_hours | ADR-007 |
| A_STABLE_EVENT_ID | manual: Paylane sends the same event_id on every retry. Attested by p_anika on 2026-09-02, review by 2027-03-01 (valid at demo time) | ADR-007 |
| A_ACK_BEFORE_TIMEOUT | webhook.ack_timeout_ms < paylane.delivery_timeout_ms | ADR-007 |
| A_CHARGE_BEFORE_TIMEOUT | paymentservice.charge_timeout_ms < checkoutservice.payment_timeout_ms | ADR-009 |
| A_RATE_TTL | currency.cache_ttl_minutes <= 60 | ADR-003 |
| A_RATES_SOURCE | manual: the rate provider publishes daily. Attested by p_tess on 2026-03-30, review by 2026-09-30 (**expired** at demo time, so G_RATES_FRESH is unknown on main) | ADR-003 |
| A_EMAIL_BUDGET | emailservice.retry_max_attempts <= emailprovider.max_retries | ADR-011 |
| A_AD_CACHE | adservice.cache_ttl_seconds <= 300 | ADR-020 |
| A_CART_TTL (orphan, required by no guarantee) | cartservice.session_ttl_hours <= 168 | ADR-005 |

### 12.4 Decisions and guarantees

| Decision | Status | Governs | Relies on | Provides (requires) |
| --- | --- | --- | --- | --- |
| ADR-003 Cache currency rates | accepted | currencyservice | | G_RATES_FRESH (A_RATE_TTL, A_RATES_SOURCE) |
| ADR-005 Cart sessions in Redis | accepted | cartservice | | none; declares A_CART_TTL |
| ADR-007 Deduplicate Paylane webhooks at ingress | accepted | webhookingress | | G_DEDUPE (A_RETRY_WINDOW, A_REDIS_TTL, A_STABLE_EVENT_ID); G_ACK_FAST (A_ACK_BEFORE_TIMEOUT) |
| ADR-009 Checkout waits for the charge result | accepted | checkoutservice | | G_NO_DOUBLE_SUBMIT (A_CHARGE_BEFORE_TIMEOUT) |
| ADR-010 Idempotency keys on every charge | superseded by ADR-012 | paymentservice | G_DEDUPE | none; text mentions retries heavily (a decoy) |
| ADR-011 Email retries within provider budget | accepted | emailservice | | G_EMAIL_WITHIN_BUDGET (A_EMAIL_BUDGET) |
| ADR-012 Payment service skips its own idempotency check | accepted | paymentservice | G_DEDUPE | G_CHARGE_ONCE (G_DEDUPE); text never mentions retries |
| ADR-015 Refunds computed from charge records | accepted | refundworker | G_CHARGE_ONCE | G_REFUND_MATCH (G_CHARGE_ONCE) |
| ADR-016 Mute Paylane delivery failure alerts | accepted | webhookingress | G_ACK_FAST | none; text cites ADR-007 and mentions retries (a decoy) |
| ADR-018 Nightly ledger reconciliation | accepted | paymentservice | G_CHARGE_ONCE, G_REFUND_MATCH | G_LEDGER_CONSISTENT (G_CHARGE_ONCE, G_REFUND_MATCH) |
| ADR-020 Cache ad inventory | accepted | adservice | | G_ADS_FRESH (A_AD_CACHE) |

Guarantees and ABOUT: G_DEDUPE (webhookingress), G_ACK_FAST (webhookingress), G_CHARGE_ONCE (paymentservice), G_REFUND_MATCH (refundworker), G_LEDGER_CONSISTENT (paymentservice), G_NO_DOUBLE_SUBMIT (checkoutservice), G_RATES_FRESH (currencyservice), G_EMAIL_WITHIN_BUDGET (emailservice), G_ADS_FRESH (adservice).

G_LEDGER_CONSISTENT reaches A_RETRY_WINDOW through two paths (via G_CHARGE_ONCE and via G_REFUND_MATCH): the diamond case.

Text sources: 4 runbooks, 20 tickets, 40 chat messages, written once with an LLM from short briefs, reviewed, committed, and disclosed in the README.

**Authoring rule for the lexical gap (test T13).** The bodies and titles of ADR-012, ADR-015, and ADR-018 must not contain any of: retry, retries, retrying, Paylane, window, webhook, 72, dedupe TTL. ADR-007, ADR-010, and ADR-016 should use those words freely. A script in `tests/` greps for this so a later edit cannot silently break the demo's central claim.

### 12.5 Scenarios and ground truth (`scenarios/scenarios.yaml`, evaluated at 2026-10-16T00:00Z)

| ID | Change | Verdict | Must include | Must exclude |
| --- | --- | --- | --- | --- |
| S1 | paylane.retry_window_hours 24 to 72 | BLOCKED (R_BROKEN_T1) | violated A_RETRY_WINDOW; broken G_DEDUPE, G_CHARGE_ONCE, G_REFUND_MATCH, G_LEDGER_CONSISTENT (once); flagged ADR-007 (promises), ADR-012 (relies_on, promises), ADR-015, ADR-018; ADR-012 routed to p_jun; not affected ADR-016; rejected fix {ttl 72}; verified fix {ttl 72, redis 72} | ADR-016, ADR-010, ADR-009 flagged; p_dev, p_marco, p_lena as reviewers; any fix touching paylane.* |
| S1_FIXED | S1 plus TTL 72 and Redis max 72 | CLEAR (R_ALL_HOLD) | all four guarantees hold on every prerequisite, including the attested A_STABLE_EVENT_ID; ADR-016 checked and not affected | any unknown guarantee |
| S2 | emailservice.retry_max_attempts 5 to 8 | CLEAR (R_ALL_HOLD) | A_EMAIL_BUDGET holds | any flag |
| S3 | delete dedupe.ttl_hours key | NEEDS_REVIEW (R_UNKNOWN) | A_RETRY_WINDOW and A_REDIS_TTL unevaluable; G_DEDUPE chain unknown | BLOCKED; CLEAR |
| S4 | dedupe.ttl_hours set to "24h" | NEEDS_REVIEW (R_UNKNOWN) | unevaluable via type mismatch | CLEAR |
| S5 | paymentservice.charge_timeout_ms 800 to 1500 | BLOCKED | broken G_NO_DOUBLE_SUBMIT; flagged ADR-009; verified fix {checkoutservice.payment_timeout_ms 1501} | ADR-012 flagged |
| S6 | adservice.cache_ttl_seconds 120 to 600 | NEEDS_REVIEW (R_BROKEN_LOW_TIER) | broken G_ADS_FRESH; flagged ADR-020 | BLOCKED |
| S7 | edit text of adr/ADR-012.md | NEEDS_REVIEW (R_MODEL_CHANGE) | reason present | CLEAR |
| S8 | edit README.md | CLEAR (R_NO_TRACKED_FACTS) | | any flag |
| S10 | cartservice.session_ttl_hours 72 to 200 | NEEDS_REVIEW (R_ORPHAN_ASSUMPTION) | violated A_CART_TTL, no guarantee | BLOCKED |
| S11 | S1 and S5 together | BLOCKED | both chains; two clusters; per cluster fixes as in S1 and S5; verified combined fix {webhook.dedupe_ttl_hours 72, redis.max_ttl_hours 72, checkoutservice.payment_timeout_ms 1501} (or the variant with charge timeout 999) | a combined fix that was not verified as a whole |
| S12 | currency.cache_ttl_minutes 30 to 45 | NEEDS_REVIEW (R_UNKNOWN, pre_existing) | A_RATE_TTL holds; A_RATES_SOURCE unverified (expired attestation); G_RATES_FRESH unknown | CLEAR (the old design would have reported it healthy) |

---

## 13. Tests that prove the graph reasoning

Unit and scenario tests run against a real FalkorDB server, each in its own `premise_test_<uuid>` graph, ingested from `sandbox/kestrel-platform` or from a temporary copy edited by the test. GitHub calls use `httpx.MockTransport`. The LLM is replaced by a scripted stub in tests.

| Test | What it proves | Setup and assertion |
| --- | --- | --- |
| T1 Predicates | Operators and operand forms are correct | Each operator, fact vs fact and fact vs const, holding and violating cases; assert `holds` |
| T2 Unevaluable | Missing data never passes | Overlay deletes a key: `holds` is null (not the main value); string vs int: null; unknown op: null |
| T3 Overlay isolation | Assessing a PR never changes main | After S1 assessment, main E1 and Fact values are unchanged; main health still all holding |
| T4 Transitive propagation | Failures reach every dependent guarantee | S1: broken set and witness chains equal ground truth, e.g. `[G_REFUND_MATCH, G_CHARGE_ONCE, G_DEDUPE, A_RETRY_WINDOW]` |
| T5 No over propagation | The BUILDS_ON flaw is fixed | S1: ADR-016 and G_ACK_FAST not flagged although ADR-016 cites ADR-007 and mentions retries; ADR-016 appears in Q2b; S5 does not flag ADR-012 |
| T6 Three valued AND and attestations | Broken dominates unknown; unknown dominates holds; manual assumptions need a current attestation | A guarantee requiring a violated and an unverified assumption is broken; unverified plus holding is unknown; a parent of an unknown guarantee is unknown. Attestation missing, expired, future dated, or by a departed person: unverified; current by an active person: holding |
| T7 Diamond and independent paths | No double counting; no false clearing | S1: G_LEDGER_CONSISTENT reported once; a guarantee requiring two independent assumptions stays broken when only one of them is fixed |
| T8 Lifecycle | Superseded decisions never count | ADR-010 never flagged; a guarantee whose only provider is superseded raises R_NO_PROVIDER |
| T9 Structural limits | Bad models are rejected, not half loaded | Ingestion fails on a REQUIRES cycle and on depth 7; a depth 6 chain is found; failed ingestion leaves state not ready |
| T10 Routing | Accountability survives departures | ADR-012 routes to p_jun (evidence 6) over p_anika; p_dev (leave), p_tess (membership ended) excluded; ties ordered by id; a decision with no candidate yields R_UNROUTABLE |
| T11 Policy table | Every rule fires correctly | S1 to S11 verdicts and reason codes equal ground truth |
| T12 Fix verification | The agent cannot propose unproven fixes | Repair rejects {ttl 72} with A_REDIS_TTL and verifies {ttl 72, redis 72}; S11 yields two clusters and a combined fix verified as a whole; never touches external facts; a stubbed LLM fix that was not tested is discarded; a stubbed LLM fix that tested false is discarded |
| T13 Lexical gap | Graph reaches what text search cannot | Fulltext over decision passages for S1's changed keys and PR title returns ADR-007 (and decoy ADR-016) but not ADR-012, ADR-015, ADR-018; Q2 returns all three and excludes ADR-016 |
| T14 Ingestion idempotency and sweep | The graph stays current and exact | Ingest twice: identical node and edge counts; remove `relies_on: G_CHARGE_ONCE` from ADR-015 and ingest R+1: ADR-015 no longer flagged by S1; old Assessment nodes still present |
| T15 Provenance | Every claim has a correct line | Every Decision, Guarantee, Assumption has STATED_IN and every Fact DEFINED_IN; the file line at each recorded number contains the id or key |
| T16 Graph required | Rule 3 holds by construction | FalkorDB stopped or `ingest_state = ingesting`: verdict ERROR, status `error`, no comment, no fix PR |
| T17 Staleness | No action on outdated knowledge | Head sha changes between assessment and execution: actions skipped, PR requeued |
| T18 Idempotent actions | Retries do not duplicate | Reassessing the same head updates one comment; one fix PR per key; an Action left `executing` is reconciled to `done` by marker search |
| T19 Analyst verification | Answers cannot cite what tools did not return | Stub LLM answer naming ADR-099 is rejected and replaced by the row fallback; `not_in_graph` outcome for an unknown topic |
| C1a Red to green needs a current attestation | Correction 1 | Move A_STABLE_EVENT_ID's attestation to a departed person: S1_FIXED becomes NEEDS_REVIEW with four unknown guarantees |
| C1b Expired attestation | Correction 1 | review_by before now: S1_FIXED is NEEDS_REVIEW with only R_UNKNOWN |
| C1c Main health | Correction 1 | G_RATES_FRESH is unknown on main, not holds |
| C2a Unchanged fact violation | Correction 2 | Main has Redis max 12 h; a PR that only shortens the retry window (A_RETRY_WINDOW holds) is still BLOCKED because G_DEDUPE is broken through the unchanged A_REDIS_TTL; reasons marked pre_existing |
| C2b Fix needs every prerequisite | Correction 2 | With A_STABLE_EVENT_ID unverified, S1 yields no verified fix; TTL 72 plus Redis 72 is partial |
| C2c Fix repairs unchanged facts too | Correction 2 | Main has Redis max 12 h: TTL 72 alone is never verified; TTL 72 plus Redis 72 is |
| C2d Not affected means evaluated | Correction 2 | Main acks in 6000 ms: G_ACK_FAST is broken before the PR; for S1, ADR-016 is listed as checked with a problem, not as not affected, and is not flagged |
| C3 No sampling parameters (agent milestone) | Correction 3 | Every request built by `agent/llm.py` lacks temperature, top_p, top_k, forced tool_choice, and prefill |
| T20 End to end (manual, rehearsal) | The demo works on real GitHub | Open S1 PR: failure within 30 s; comment contains ADR-012, ADR-015, ADR-018 and lists ADR-016 as not affected; fix PR opened; merge it; S1 PR success within 30 s |

`premise scenarios` runs every scenario through the CLI pipeline and prints a pass/fail table; the same table goes in the README.

**Mutation check (done Oct 16):** each correction was temporarily reverted to the revision 1 behaviour. Old manual semantics: 7 tests fail. Old changed facts only scope: 7 tests fail. Old "absent means not affected": 1 test fails (C2d). Restored code: 47 of 47 pass.

---

## 14. Implementation plan (IST)

Gates are hard. Missing a gate removes optional items first, then UI polish, never tests or the README.

### Progress as of Fri Oct 16, 03:45 IST

- [x] FalkorDB v4.18.3 running; section 15 construct checklist passed (16 of 16)
- [x] M1 sandbox data (12 services, 10 people, 11 ADRs, 9 guarantees, 10 assumptions, 12 facts, 14 tickets, 6 chat messages, 2 runbooks); scenarios.yaml with 12 scenarios
- [x] M2 ingestion: parsers with line numbers, validation rules 1 to 9, revisions with sweep, indexes, mention resolver
- [x] M3 reasoning: E1, Q1, Q2, Q2b, Q3, policy, deterministic repair; 47 of 47 tests pass
- [ ] Create `premise` and `kestrel-platform` repos on GitHub; register the team; ask the FalkorDB Discord whether one submission can be judged in two tracks
- [ ] M4 onward as planned below; M1 to M3 rows in the Friday table are done

### Fri Oct 16

| Time | Milestone | Exit criterion |
| --- | --- | --- |
| 09:00 to 12:00 | M1 Sandbox repo: catalog, people, teams, 11 ADRs, facts.yaml, config files, runbooks; scenario branches; expected.yaml; mini_company fixture | validation passes by hand checklist |
| 12:30 to 16:30 | M2 Ingestion: parsers with line numbers, validation, load, sweep, GraphState, indexes, mention resolver | T9, T14, T15 pass |
| 17:00 to 20:00 | M3 Reasoning: E1, Q2, Q2b, Q3, policy, repair | T1 to T8, T10, T11, T13 pass, no LLM, no GitHub |
| 20:30 to 23:30 | M4 Intake: git clone, merge base diff, overlay, ChangeProposal; `premise assess --pr N --json` | S1 from a real PR prints the correct result |
| **24:00** | **Gate 1** | deterministic pipeline correct on all scenarios |

### Sat Oct 17

| Time | Milestone | Exit criterion |
| --- | --- | --- |
| 09:00 to 12:00 | M5 GitHub: poller, status, comment upsert, Mermaid render, Action nodes, idempotency, staleness, reconcile | T16 to T18 pass; real S1 PR goes red with comment |
| **12:00** | **Gate 2** | first real red PR |
| 12:30 to 15:30 | M6 Fix agent: tools, LLM loop, controller, stacked fix PR with line edit | T12 passes; merging the fix PR turns S1 green |
| 16:00 to 18:30 | M7 Track 3: Analyst with verification; MCP server; test in MCP Inspector then Claude Desktop | T19 passes; 3 demo questions answered |
| 19:00 to 22:00 | M8 UI: Brain, assessment, entity pages; PageRank tool; lexical gap panel | status link opens the assessment page |
| 22:00 to 23:30 | Full rehearsal; record fallback video | **Gate 3: a complete fallback video exists** |

### Sun Oct 18

| Time | Work |
| --- | --- |
| 09:00 to 11:30 | Optional items in order O1, O2, O3, only if Gate 3 was met |
| **11:30** | **Feature freeze** |
| 11:30 to 14:00 | README: product, tracks, setup, graph model, every Cypher file linked, test table, scenario table, limitations, AI disclosure; fresh clone test |
| 14:00 to 17:00 | Final video: record, edit to 3:00, upload |
| 17:00 to 20:00 | Buffer; blog only if everything else is done |
| 20:00 to 21:00 | Submit; verify public repos, video plays logged out, setup works, both tracks named |

### Two person split

| Person | Owns | Interface |
| --- | --- | --- |
| A | M1, M2, M3, tests T1 to T15, README graph sections | produces `AssessmentResult` via CLI |
| B | M4, M5, M6, M7, M8, T16 to T19, video | consumes `AssessmentResult` |

Solo: follow the timeline in order; cut M8 to the assessment page only if Gate 2 slips past 14:00.

---

## 15. Verified constructs (FalkorDB v4.18.3, Oct 16)

Every construct the spec relied on was run against the real engine. All passed; no fallback is needed.

| # | Construct | Result |
| --- | --- | --- |
| 1 | `typeOf()` returns `Integer`, `Float`, `String`, `Null`, usable inside CASE and IN | passed |
| 2 | `any(...)` and a list comprehension projecting `o.to` over a list of maps parameter | passed (null values preserved) |
| 3 | `MATCH p = (g)-[:REQUIRES*1..6]->(a) WHERE a.id = h.id` after UNWIND | passed |
| 4 | ORDER BY before `collect()` preserves order for `head(collect(p))` | passed |
| 5 | List concatenation with `+` of collected lists | passed |
| 6 | Inline property maps in OPTIONAL MATCH node patterns | passed |
| 7 | Secondary label `:Entity` with one fulltext index | passed |
| 8 | `algo.pageRank('Guarantee', 'REQUIRES')` on multi labelled nodes | passed (G_DEDUPE ranks first on the sandbox) |
| 9 | `MATCH ()-[r]->() WHERE type(r) IN $types AND r.rev < $rev DELETE r` | passed |
| 10 | `count(DISTINCT CASE WHEN ... THEN a END)` | passed |
| 11 | Comparing a number with a string returns null, not an error | passed |
| 12 | `GRAPH.RO_QUERY` rejects writes | passed |

Findings while implementing, all fixed and covered by tests:

- `GRAPH.RO_QUERY` on a graph that does not exist yet is an error, so the first state read of an ingestion uses a normal query.
- YAML 1.1 reads the key `on` as the boolean true; attestation dates use `date`, and an attestation without one is a validation error.
- The order of `collect()` is not guaranteed; reviewer lists are sorted in code.
- The Redis client raises its own `ConnectionError` class; the graph client now maps it, timeouts, and lazy connection failures to `GraphUnavailable`, so an outage at any moment yields an ERROR verdict instead of a crash.

Still open: GitHub statuses and comments on a PR opened by the token owner (M5), status on a fork PR head sha, the exact Docker Hub tag for 4.18.3, and whether organizers judge one submission in two tracks (D11 applies if not).

---

## 16. Submission checklist

- [ ] `premise` public, `kestrel-platform` public, both created during the event
- [ ] README: what Premise is; tracks entered (3 and 1); one command setup (`docker compose up`, `premise ingest`, `premise serve`); env vars; graph model tables; links to every `.cypher` file; agent workflow; real vs simulated actions (no simulated actions in the MVP); test and scenario tables with actual results; limitations (numeric predicates only, edited ADRs evaluated after merge, polling, single process, synthetic data); AI tools disclosure (coding assistants used, synthetic text generated by an LLM and reviewed)
- [ ] Demo video, at most 3 minutes, plays logged out
- [ ] Live deployment URL or complete local setup verified from a fresh clone
- [ ] Track names entered in the submission form
