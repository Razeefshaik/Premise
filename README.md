<div align="center">

<a href="https://razeefshaik.github.io/Premise/"><img src="docs/media/banner.png" alt="Premise: a pull request changes the Paylane retry window from 24 to 72 hours, and the Kestrel company brain lights the broken path through four guarantees" width="100%"></a>

<br><br>

[![Tests](https://github.com/Razeefshaik/Premise/actions/workflows/tests.yml/badge.svg)](https://github.com/Razeefshaik/Premise/actions/workflows/tests.yml)
[![Live replay](https://github.com/Razeefshaik/Premise/actions/workflows/pages.yml/badge.svg)](https://razeefshaik.github.io/Premise/)
![FalkorDB 4.18.3](https://img.shields.io/badge/FalkorDB-4.18.3-5b63ff)
![Red team 35/35 safe](https://img.shields.io/badge/red%20team-35%2F35%20safe-2ea043)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab)

### [▶&nbsp; Try the live replay](https://razeefshaik.github.io/Premise/) &nbsp;·&nbsp; [🎬&nbsp; Watch the demo](https://razeefshaik.github.io/Premise/explore.html?story=1) &nbsp;·&nbsp; [🔴→🟢&nbsp; See a real PR go red, then green](#the-real-github-flow)

<sub>The live replay is a <b>read-only recording</b> of real FalkorDB results, so anyone can explore it without installing anything.<br>
For the <b>full version</b> (live What if checks, Ask the company, PR assessments, verified fix PRs and the MCP server for coding agents),
<a href="#run-locally"><b>run it locally in two commands</b></a>.</sub>

[The company brain](#the-company-brain) · [How it is built](#how-the-brain-is-built) · [Ask the company](#ask-the-company) · [When a change arrives](#when-a-change-arrives) · [Graph data model](README_DETAILED.md#graph-data-model) · [Cypher and algorithms](README_DETAILED.md#cypher-and-graph-algorithms) · [Benchmark](#benchmark-what-does-structure-buy) · [Run locally](#run-locally)

</div>

---

## The company brain

**Premise connects what your company decided, why it decided it, who knows the context, and what must remain true.** Decision records, config, tickets, chat and runbooks become a connected, queryable model in FalkorDB.

A decision links to the promises it makes. Each promise links to its assumptions and real config values. People, teams and source passages supply ownership and evidence. You can follow those connections to understand a decision, find a reviewer, or see which knowledge is becoming unreliable.

![The real Decision Explorer connects decisions, guarantees, services, people and teams](docs/media/10-brain-people.jpg)

*Explore the relationships, click a node for evidence, or trace the path between two nodes.*

## How the brain is built

**Read supported sources → connect their meaning → answer from the graph.**

```mermaid
flowchart LR
  S["Decisions, config, tickets<br/>chat, runbooks and people"] --> P["Deterministic parsing<br/>references and source lines"]
  P --> G[(FalkorDB decision graph)]
  G --> A["Answers with evidence"]
  G --> K["Ownership and knowledge gaps"]
  G --> C["Change checks and verified fixes"]
```

1. **Read and validate.** Parsers extract typed entities from reviewed files, validate references and dependency chains, and retain source locations.
2. **Connect.** Explicit relationships capture what a decision provides, what a guarantee requires, who is accountable, and which passages mention it. Service names and aliases connect related evidence.
3. **Query and explain.** Shared graph tools power the web app, answers and coding-agent checks. The Explorer exposes the Cypher, parameters and timing behind its results.

The included fictional company demonstrates **88 sources → 275 nodes and 488 relationships**, with 120 source passages. It is a working dataset for exploring the product, not the boundary of the idea.

**Keeping knowledge current:** the experimental v2 pipeline consumes source events, grounds claims in quotes, groups independent evidence, and proposes reviewed updates. Slack/Jira use fixtures; GitHub supports read-only live intake. Evidence stays separate from the decision graph until a human-approved change is ingested. [Pipeline details](docs/V2.md).

**Why FalkorDB:** dependency paths, evidence lookup, assessment history, continuity algorithms and the vector-search benchmark all use the same datastore. **Models may propose or explain; deterministic queries and code decide verdicts.**

## Ask the company

| Your question | What Premise connects |
| --- | --- |
| **Why did we make this decision?** | Decision history, promised guarantees, assumptions and cited source passages. |
| **Who should review it now?** | Current people, accountability and recent authored evidence. |
| **What if this person leaves?** | Orphaned decisions, unverified promises and alternative reviewers. |
| **What becomes uncertain next month?** | Attestation expiry dates and the guarantees that depend on them. |

![A real decision page shows reasoning paths, current reviewers and evidence counts](docs/media/11-entity-adr012.jpg)

*The decision page brings dependency paths and reviewer evidence together. Ask the company provides cited answers in the local app; continuity and the time machine let you explore departures and future dates.*

Coding agents use the same knowledge through **11 read-only MCP tools**, including checks before editing files. [MCP setup](README_DETAILED.md#agents-and-mcp).

## When a change arrives

Because the brain records dependencies, it can trace the consequences of a changed fact, even when a downstream decision never mentions that fact.

**One demonstration:** a partner's retry window changes from 24 to 72 hours. Four guarantees fail. Raising deduplication alone would exceed the Redis limit, so Premise verifies a remedy that raises both limits.

![Failure travels through the real graph, then the verified remedy restores the affected guarantees](docs/media/propagation.gif)

**Trace the affected promises → report BLOCKED with reviewers → propose a verified fix → reassess after human merge.** Fixes are verified within the recorded model; Premise never merges them automatically. Missing or expired evidence produces uncertainty rather than a false assurance.

### The real GitHub flow

[Original PR #1](https://github.com/Razeefshaik/kestrel-platform/pull/1) → [verified fix PR #2](https://github.com/Razeefshaik/kestrel-platform/pull/2) → human merge → **CLEAR_WITHIN_SCOPE**. [Recorded status timeline](README_DETAILED.md#the-real-github-flow).

## Benchmark: what does structure buy?

We compared graph reasoning, keyword search and vector RAG on FalkorDB, including questions about both **company knowledge** and **change impact**.

![Macro F1 comparison for change impact, company-brain questions and all test questions](docs/media/benchmark-f1.png)

Across all 30 test questions, macro F1 is **0.79 graph · 0.30 vector · 0.25 keyword**. On the 15 company-brain questions, it is **0.58 · 0.14 · 0.24**; on the 15 change-impact questions, **1.00 · 0.46 · 0.27**. The chart shows the best tested retrieval setting for each subset.

**Scope:** authored synthetic questions and company data, with human label review pending. The graph has explicit dependencies; retrieval searches ADR passages. These results measure the benefit of that structure, not general intelligence. [Methods, every setting and raw results](docs/BENCHMARK.md).

## Results and evidence

| Recorded result | Evidence |
| --- | --- |
| **348 tests passed · 12/12 scenarios** | [Validation record](docs/VALIDATION.md) · [CI workflow](.github/workflows/tests.yml) |
| **35/35 red-team cases reached the expected safe outcome** | [Attacks and report](docs/REDTEAM.md); a regression suite, not security certification. |
| **Real statuses and a stacked fix PR** | [GitHub rehearsal](README_DETAILED.md#the-real-github-flow); fixes require human merge. |
| **Inspectable reasoning** | [Cypher queries and graph algorithms](README_DETAILED.md#cypher-and-graph-algorithms), source provenance and recorded assessments. |

## Run locally

From this checkout, with Docker Desktop's Linux engine running:

```bash
docker compose up --build -d
docker compose exec app premise demo
```

Open **[localhost:8000](http://localhost:8000)**. No API keys are needed for the local demo. Real GitHub actions require explicit setup and a sandbox token: [publishing guide](docs/PUBLISH.md).

**Stack:** Python · FastAPI · FalkorDB · Cypher · GitHub API · MCP

**Hackathon:** built by Shaik Mahammad Razeef for WeMakeDevs × FalkorDB Graph Hacks. **Track 3: Company Brain** and **Track 1: Agents That Act on Connected Data**.

**Current scope:** a single-company prototype using fictional data. The public site is a read-only replay; live questions and PR assessments run locally. [Full capabilities and limits](README_DETAILED.md).

**AI use:** Claude and OpenAI Codex assisted with implementation, review, tests, documentation and synthetic data. [Disclosure and attribution](README_DETAILED.md#ai-use-disclosure).

[Detailed README](README_DETAILED.md) · [Architecture](docs/DESIGN.md) · [Evidence pipeline](docs/V2.md) · [Replay](docs/REPLAY.md) · [Demo guide](docs/DEMO.md)
