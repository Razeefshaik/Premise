# Premise v2 review fixes: validation

Validated on Windows with Python 3.13 and the real FalkorDB 4.18.3 Compose service, 2026-10-16.
Branch: `v2/self-maintaining-brain`. Specification: [Premise_v2_Fix_Spec.md](Premise_v2_Fix_Spec.md).
Implementation baseline: `5f60595`; the existing bundle-only commit `8d62130` was preserved.
No files under `premise/` were modified. No commits were pushed and no real GitHub PRs were changed.

## Regression evidence

Every finding and the connection-error improvement had a regression fail before its implementation
changed. The permanent regressions are in `tests/test_v2_fixes.py`, using real graphs/streams and
the existing `FakeGitHub`. All v2 tests were run after each fix.

| Fix | Observed failure before fix | Commit | Passing v2 tests after fix |
| --- | --- | --- | --- |
| 1: graph isolation | Four unsafe configurations reached connection construction | `9b5d605` | 47 |
| 2: quote visibility | Private denial and speculative text appeared in the body | `2c12a7c` | 48 |
| 4: thread origins | Root plus reply was corroborated | `d9f34ec` | 49 |
| 3: connector scopes | Two false tombstones; older second-channel message skipped | `f6d1c78` | 52 |
| 7: version watermark | Delayed v2 was stored after unchanged v3 | `7a39bd0` | 53 |
| 8: recovery and catch-up | Pending pagination stopped early; publication proceeded with pending work | `d63f886` | 57 |
| 5: dry run to live | Zero PRs were opened on the first live run | `a029ce9` | 58 |
| 6: withdrawal | Unsupported proposals stayed open locally and remotely | `da04162` | 63 |
| Extra: friendly database error | Port 1 returned code 1 with a traceback | `4e295eb` | 64 |

Withdrawal tests also verify a new PR after evidence returns, local-only dry withdrawal, and
retry after an interrupted or deferred remote closure without creating a human rejection.
The original live-update test now invalidates `published_hash`, rather than the local `body_hash`,
to request a remote update under the new separation of document and publication state.

## Final checks

- Full suite: **217 passed**, one existing Starlette/httpx deprecation warning, in 185.78 seconds.
- Final v2 suite: **64 passed** in 54.97 seconds, including 21 new regression cases.
- `premise-v2 registry-check`: **registry ok**, exit 0.
- `premise-v2 eval`: **10/10 correct claims**, precision/recall 1.0, **1/1 expected drift**,
  zero false-positive drifts, **0/6 decoys promoted**, **4/4 fabricated claims rejected**,
  1/1 expected secret redaction, 13 stream entries processed and zero pending.
- Review probes: **all eight passed**, exit 0. Disposable graphs and streams were cleaned up.
- `git diff --exit-code 5f60595 -- premise/`: passed; v1 sources are unchanged.
- `git diff --check`: passed.

The review probe's `live_keys` calls were adapted to its new connector-scope contract. Its
withdrawal observation now checks the banner, closed PR, local withdrawn state and absence of
human rejection. The old quoted evidence intentionally remains below the withdrawal banner as
history. The original probe and results were retained locally as `probes-before-fixes.py` and
`results-before-fixes.json`; current observations are in `.runtime/v2-review/results.json`.
These `.runtime` artifacts are ignored by Git; the permanent tests above travel with the code.

## Reproduce

From the repository root in PowerShell, with FalkorDB running:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\premise-v2.exe registry-check
.\.venv\Scripts\premise-v2.exe eval
.\.venv\Scripts\python.exe .runtime/v2-review/probes.py
```

The CLI entry point was refreshed with an editable local installation. GitHub lifecycle checks
use `FakeGitHub`; this validation does not claim a live GitHub rehearsal. Phase 1 still uses the
small synthetic fixture corpus and a rule-based extractor, so these scores do not establish
accuracy on real company conversations.
