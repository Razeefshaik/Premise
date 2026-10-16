# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Engineers and reviewers at a software company who change configuration and code, and need to know
  which architecture decisions a change touches before they merge it.
- Hackathon judges (WeMakeDevs × FalkorDB Graph Hacks, Track 1 and Track 3) seeing the product for the
  first time in a live demo or recording. They have about three minutes and must understand what Premise
  is from the first screen. (Inferred from README and docs/DEMO.md; confirmed by the user's request for
  a first-time-visitor hero.)

## Product Purpose

Premise is a company brain for engineering decisions. It connects architecture decisions to the
guarantees they promise or rely on, guarantees to their prerequisite assumptions, and assumptions to
current facts and dated human attestations, all in FalkorDB. When a pull request or a hypothetical
change moves a fact, Premise traces the consequences, gives a deterministic verdict (BLOCKED,
NEEDS_REVIEW, CLEAR_WITHIN_SCOPE), routes review to the people who know why, and verifies complete
remedies before any fix PR is opened.

## Positioning

It reaches decisions whose text never mentions the changed fact (the lexical gap): ADR-012, ADR-015 and
ADR-018 are reached through the guarantee graph, while ADR-016 is explicitly checked and shown as not
affected. Verdicts are deterministic graph policy; no model can pass or fail a check.

## Operating Context

FastAPI + Jinja web app (`premise/web`), served locally on port 8000 next to the FalkorDB Browser. Also
reachable through the CLI, an MCP server for coding agents, and GitHub commit statuses and comments.
Pages: Company Brain (`/`), PR assessment (`/assessments/{id}`), What-if preflight (`/what-if`),
entity explorer (`/entities/{id}`), and an unavailable-graph error page.

## Capabilities and Constraints

- Three-valued guarantee health: broken dominates unknown, which dominates holds.
- What-if is read-only; nothing is stored or posted. External facts are labelled.
- The Analyst answers questions from eleven read-only graph tools, with cited sources.
- The web UI has no authentication and binds to loopback.
- No invented counts, progress, scores or model results may appear in the UI.

## Brand Commitments

Name: Premise. Footer line: "Every guarantee needs evidence. Every verdict has a path." Kestrel
Platform is a fictional company and must stay labelled as fictional. "Powered by FalkorDB".

## Evidence on Hand

The fictional Kestrel dataset (`sandbox/kestrel-platform`), scenarios S1–S12 (`scenarios/scenarios.yaml`),
four local demo assessments created by `premise demo`. No customers, testimonials, press or usage
statistics exist; none may be invented.

## Product Principles

1. Every state is shown with its evidence and its path, never as a bare score.
2. Unknown is never shown as healthy.
3. The interface never claims more than the graph returned.
4. Hypothetical exploration is safe and says so.

## Accessibility & Inclusion

Colour always accompanies a written state. Keyboard focus is visible. Motion has a reduced-motion path.
