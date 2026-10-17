<div align="center">

<a href="https://razeefshaik.github.io/Premise/"><img src="docs/media/banner.png" alt="Premise traces a changed retry window through the company brain to the engineering promises it breaks" width="100%"></a>

# Premise

**The company brain for engineering decisions.**

Search finds documents. Premise finds consequences.

[![Tests](https://github.com/Razeefshaik/Premise/actions/workflows/tests.yml/badge.svg)](https://github.com/Razeefshaik/Premise/actions/workflows/tests.yml)
[![Live replay](https://github.com/Razeefshaik/Premise/actions/workflows/pages.yml/badge.svg)](https://razeefshaik.github.io/Premise/)
![FalkorDB](https://img.shields.io/badge/FalkorDB-4.18.3-5b63ff)

**[Try the interactive replay](https://razeefshaik.github.io/Premise/) · [See the real fix PR](https://github.com/Razeefshaik/kestrel-platform/pull/2) · [Detailed guide](README_DETAILED.md)**

Built by **Shaik Mahammad Razeef** for **WeMakeDevs × FalkorDB Graph Hacks**

Track 1: Agents That Act on Connected Data · Track 3: Company Brain

</div>

## Why Premise?

Your company knows why it built things. That knowledge is scattered across decision records, config files, tickets, chat and runbooks. When something changes, the promises that depend on it are easy to miss.

**Premise connects those sources, their owners and their dependencies in FalkorDB.** Ask why a decision exists, see who should review it, or check which promises a pull request would break. Every verdict comes from deterministic graph queries and code.

## Watch one change break four promises

A payment partner extends its retry window from **24 to 72 hours**, but webhook deduplication still lasts only 24 hours. Premise traces the dependency chain to **four broken guarantees**, flags the PR as **BLOCKED**, and identifies reviewers.

Raising the deduplication window alone exceeds Redis's configured maximum. Premise verifies a fix that raises **both** limits before opening a fix PR. A human merges it; reassessment returns **CLEAR_WITHIN_SCOPE**.

![A changed retry window breaks dependent guarantees, then a verified fix heals them](docs/media/propagation.gif)

**Try it:** open the [replay](https://razeefshaik.github.io/Premise/), choose **Play the story**, and watch the failure travel through the graph. The replay contains recorded FalkorDB responses; live questions and GitHub actions require the local app.

**Real GitHub evidence:** [original PR #1](https://github.com/Razeefshaik/kestrel-platform/pull/1) → [verified fix PR #2](https://github.com/Razeefshaik/kestrel-platform/pull/2) → [assessment timeline](README_DETAILED.md#the-real-github-flow).

## What you can do

| Feature | What it gives you |
| --- | --- |
| **Ask the company** | Answers about decisions, dependencies and reviewers, with source citations. |
| **Explore consequences** | An interactive graph, hypothetical checks, and the exact Cypher behind each result. |
| **Check and repair PRs** | Commit statuses, an updatable explanation, and a fix PR only after complete verification within the model. |
| **Forecast knowledge gaps** | A time machine for expiring attestations and a continuity view for hypothetical departures. |
| **Guide coding agents** | 11 read-only MCP tools, including checks before an agent edits a config file. |
| **Propose knowledge updates** | An experimental evidence pipeline that grounds claims in source quotes and proposes changes for human review. |

## Why a graph? Why FalkorDB?

A downstream decision may never mention the config value it depends on. Premise follows explicit `REQUIRES` paths from changed facts through assumptions and guarantees to affected decisions. People and source passages explain who knows the context and where the reasoning came from.

**FalkorDB is the only datastore:** it powers dependency traversal, evidence lookup, assessment history, continuity algorithms and the vector-search benchmark. Models can help propose or explain; they never decide verdicts or directly update the decision graph.

**Stack:** Python · FastAPI · FalkorDB · Cypher · GitHub API · MCP

## Evidence and limits

| Recorded result | Inspect it |
| --- | --- |
| **348 tests passed · 12/12 scenarios** | [Validation](docs/VALIDATION.md) and [CI](.github/workflows/tests.yml) |
| **35/35 red-team cases reached the expected safe outcome** | [Attack cases and report](docs/REDTEAM.md) |
| **Change-impact F1: graph 1.00 · vector RAG 0.46 · keyword 0.27** | [Benchmark, methods and caveats](docs/BENCHMARK.md) |

The benchmark uses 15 authored change-impact test questions about **Kestrel, a fictional company**; it is not a general QA claim. This is a single-company prototype. Slack/Jira intake uses fixtures; GitHub intake can run read-only. Knowledge updates require human review, and fix PRs are never merged automatically.

## Run locally

From this checkout, with Docker Desktop's Linux engine running:

```bash
docker compose up --build -d
docker compose exec app premise demo
```

Open **[localhost:8000](http://localhost:8000)**. No API keys are needed for the local demo. Real GitHub actions are opt-in and need a sandbox token: [setup instructions](docs/PUBLISH.md).

**Go deeper:** [Full README](README_DETAILED.md) · [Architecture](docs/DESIGN.md) · [Evidence pipeline](docs/V2.md) · [Replay](docs/REPLAY.md) · [Demo guide](docs/DEMO.md)

**AI use:** Claude and OpenAI Codex helped with implementation, review, tests, documentation and synthetic data. [Disclosure and attribution](README_DETAILED.md#ai-use-disclosure).
