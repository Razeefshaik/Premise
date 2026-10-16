# Phase 2 implementation and validation

Branch `v2/phase-2` starts at fixed Phase 1 commit `d07da35`. The submission branch and `premise/`
are preserved. The design is [Premise_v2_Phase2_Design.md](Premise_v2_Phase2_Design.md).

## Package results

| Package | Implemented behavior | Full-suite result |
| --- | --- | --- |
| P2.1 | Dict checkpoints, failure records/retries, four connector interfaces, read-only GitHub, exported Pages, CODEOWNERS evidence | **224 passed**, 1 existing warning, 120.66 s |
| P2.2 | Account-based claims, reversible identity links, verified email, strict fuzzy proposals, bridge checks, shared proposal publication | **230 passed**, 1 existing warning, 145.42 s |
| P2.3 | Extractor framework, local-only model selection, schema repair/cache/budget, E3 grounding, review challenges and optional private-safe issues | **241 passed**, 1 existing warning, 120.75 s |
| P2.4 | Approved descriptive extraction, temporal knowledge proposals, unmatched mentions, explicit partners, isolated validated loader | **253 passed**, 1 existing warning, 152.23 s |
| P2.5 | Frozen 80-snippet corpus, actual Codex recordings, strict offline replay, holdout floors and CI | **261 passed**, 1 existing warning, 159.69 s |
| P2.6 | Local read-only review queue, private-safe details, registry counts and CSRF-protected staging-only dismissal | **269 passed**, 1 existing warning, 218.28 s |
| P2.7 | Grounded E1, private-only draft review, validated inactive ADR files, shared pipeline budget/cache and actual E1 recordings | **284 passed**, 1 existing warning, 285.05 s |
| Final compatibility cleanup | Backfill legacy source accounts on duplicate replay; let dismissed findings return only for newer evidence | **286 passed**, 1 existing warning, 432.88 s |

The final cleanup also passed 17 focused identity/review tests. Claim ids are preserved when
Phase 1 envelopes are replayed; reviewed link changes then re-count origins without extraction.
Re-rendering a dismissed finding keeps it hidden; newer source timestamps can restore it.
The final suite uses real FalkorDB, FakeGitHub and FakeAdapter, including strict gold replay.

P2.7 holdout E1: precision/recall/exact quotes 1.00; annotated-field accuracy 0.857
(literal title punctuation). Claim matching normalizes a terminal full stop/case in the
title, while requiring matching services, guarantees, assumption checks and requirement indexes;
optional absent nulls are equivalent. Scoring was frozen before E1 holdout capture.
Across all extractors/splits, recordings contain 29 actual Codex calls. No test calls a model.

Final checks at P2.7: registry check passed; gold holdout floors passed with no injected
grounded candidates; original fixture eval remains 10/10 correct claims, 1/1 expected
drift, 0 false drifts, 0/6 promoted decoys and 4/4 rejected fabricated claims.
No files under `premise/` differ from the submission branch; no remote push was performed.

P2.6 browser checks: queue, detail and relations at 1440x1000 and 390x844, no document
overflow, no page errors; Dismiss removes the finding. Screenshots are local ignored artifacts.
An independent finish review found no material visual defect and confirmed the copied v1
stylesheet and documented palette/type system. A real-browser failure exposed that
`Referrer-Policy: no-referrer` made the form's origin null and withheld its cookie; the
tested `same-origin` policy fixes this while withholding external referrers.

P2.5 holdout: E2/E3/Kind 2 precision and recall 1.00; exact quotes 1.00; E3
annotated-field accuracy 0.75; 0 grounded injection candidates; identity 4/4.
The corpus remains pending Razeef review. Recorded inference used 23 model calls
across both splits; the resolved backend model was not exposed by the adapter.

Tests use real FalkorDB and synthetic fixtures. GitHub API behavior is exercised through a
read-only extension of the existing FakeGitHub; no live GitHub or model calls occur in tests.

## Open specification decisions

- `token_set_ratio("Anika R.", "Anika Rao")` is 82.35, below the design's threshold of 92. The
  requested example and the specified algorithm cannot both hold without an extra abbreviation
  rule. Razeef confirmed: preserve the strict 92 threshold and use a closer name in the test.
- The 80-snippet gold corpus can be authored here, but its human-review status must remain pending
  until Razeef reviews it. Recorded outputs must come from an actual Codex run; fabricated outputs
  must never be labeled model recordings.
- v1 parses active guarantee/assumption fields regardless of proposed status. E1 therefore
  stores prospective fields under an inert `draft` key. A human must promote those fields,
  assign accountable people, accept and merge. Tests prove draft ingest preserves verdicts.
