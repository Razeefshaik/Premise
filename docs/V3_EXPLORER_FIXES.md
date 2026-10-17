# Explorer follow-up: 2026-10-17

Built on `v3/public-replay`, following the [V3 design](Premise_V3_Design.md).
Implementation: `465c3b9`; bundle removal: `dd929d8`. Both are local commits.

The hypothetical check previously changed node colours while captions and the Evidence
inspector retained baseline health. The assessment response now includes the engine's
assumption states and guarantee statuses/chains. Explorer applies those results to the
node colour, written caption and selected inspector together, keeps baseline health for
reset, and ignores superseded requests. This adds no reasoning policy or graph writes.

The verdict is above the canvas independently of the Evidence / What if tabs. Search,
depth, kinds and time controls share an inspector disclosure, so the complete canvas fits
the first screen at 1440x900 and 390x844. On mobile the inspector follows the graph.

Explorer resolves reviewer IDs through a read-only name lookup and uses names for person
headings, captions and picker options. Continuity uses its existing people response for
reviewer and graph labels. IDs remain stable internally, with a fallback when no name is
available. The tracked `premise-v2.bundle` was removed with `git rm`.

Implementation: [preflight response](../premise/reasoning/preflight.py),
[node details](../premise/web/graph_api.py), [Explorer](../premise/web/static/explore.js),
[hypothetical presentation](../premise/web/static/consequences.js),
[layout](../premise/web/templates/explore.html), and
[Continuity](../premise/web/static/continuity.js).

## Validation

| Check | Actual result |
| --- | --- |
| Full pytest suite | 342 passed in 409.28 seconds; 35 JUnit metadata warnings |
| Scenario CLI | 12/12 passed |
| `scripts/check_ui.py` | Passed; no page or console errors |
| `scripts/check_replay.py` | Passed; no browser errors, 152 requests, zero external requests |

Browser regressions in [explorer_checks.py](../scripts/explorer_checks.py) and the live
checker assert the actual Cytoscape label `G_DEDUPE\nbroken` for
`paylane.retry_window_hours=72`, its hypothetical Evidence status, the `violated`
assumption, repair to `holds`, reset to baseline, and `unknown`/`unevaluable` after a
missing fact. They also check first-screen canvas bounds and the visible verdict with
Evidence selected at both requested sizes. Continuity and Explorer assertions require
person names rather than the corresponding IDs. API coverage checks the engine's state
payload and verifies that a repaired proposal leaves baseline health unchanged.

The fresh replay export contains 3,333 responses across eight recorded dates. Its first
browser run caught the replay notice pushing the desktop canvas 6.56 pixels beyond the
900-pixel viewport. Replay-specific height rules now reserve room for the notice at
both sizes; the subsequent browser run passed. After that CSS correction the full suite
was rerun against the final application source and passed. The initial browser checker also needed its scenario
targets and collapsed time-control interaction updated; passing results above are from
the corrected checker.

A later repeat hit the local 180-second wrapper limit. A temporary line trace reproduced
the stall at the checker's redundant manual `cy.resize(); cy.fit()` call on mobile.
The checker now waits for the page's graph-loaded message and inspects the rendered
graph without that extra resize. The final traced run passed every browser assertion,
with zero page or console errors. The trace remains ignored under
`.runtime/v3-followup/ui-trace-resize-stall.txt`.

The 35 pytest warnings concern the existing red-team tests' `record_property` metadata
and the default JUnit `xunit2` report format. They are reporting warnings; the final run
had zero failures and zero errors. Full-suite text and JUnit evidence are saved in
`.runtime/v3-followup/pytest.txt` and `pytest.xml`.

Live browser/scenario validation uses a uniquely named graph and a temporary loopback
server with GitHub polling and models disabled; both are removed afterward. Generated
logs and screenshots remain ignored under `.runtime/v3-followup/`,
`.runtime/v3-validation/`, and `.runtime/v3-replay/`.

The independent visual reviewer returned **ship** for the requested refinement; see
[V3_UI_REVIEW.md](V3_UI_REVIEW.md). Dense graph labels remain a limitation at overview
scale, with readable detail available through the inspector. No public deployment,
remote push or GitHub action is performed by this follow-up.
