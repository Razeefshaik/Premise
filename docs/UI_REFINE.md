# UI refinement for the showcase

**Finished on `ui/showcase`, 2026-10-17.** All remaining pages, the propagation GIF and
validation are complete. See [Final verification](#final-verification--2026-10-17).
The audit and original handoff below are retained as the lifecycle record.

Branch `ui/showcase`, created from local `main` after fast-forwarding it to the complete V3 stack
(`v3/public-replay`, `f28fad3`). Every local and remote branch was confirmed to be contained in that
commit before the fast-forward. Nothing is pushed.

Scope: polish and animate the existing Cortex interface. Reasoning, queries, verdicts and recorded
results are unchanged. Skills applied: **impeccable** (Operate mode for working pages, Persuade for
the landing hero), **emil-design-eng** (motion purpose, easing, durations, interruptibility) and
**design-taste-frontend** (hierarchy, restraint, real content).

Before screenshots: [`artifacts/ui-before/`](../artifacts/ui-before/) — every page at 1440×900 and
390×844, first screen and full page, captured from a live app on an isolated `premise_showcase`
graph with `scripts/capture_ui.py`. All 18 captures had zero console errors and no horizontal
overflow.

## Audit

### Explorer (`/explore`)
1. The hero moment is invisible. What if lives in a second inspector tab; the S1 change recolours
   nodes with a fixed 250 ms delay per guarantee, but nothing travels: you cannot see failure move
   up the REQUIRES chain, or the fix heal it.
2. The verdict is a flat line of bold text ("Hypothetical · BLOCKED"). It does not carry the state
   colour, the counts (four guarantees, four decisions) or an icon; it reads like a caption.
3. Layout: the hypothetical view switches to a force layout (cose) whenever services are present.
   The chain A_RETRY_WINDOW → G_DEDUPE → G_CHARGE_ONCE → G_LEDGER/G_REFUND is scattered and
   labels collide ("G_DEDUPE webhookingress" overprint). Causality should read bottom to top.
4. The overview packs 30 labels into one row each; captions overlap (e.g. "A_RATE_TTLA_CHARGE…").
5. Decisions are all one lavender; affected decisions only gain a thin pink border.
6. Controls (search, depth, kinds, time machine) hide in a collapsed disclosure inside the
   inspector. The time machine, a headline feature, is two clicks away.
7. The legend is a paragraph under the canvas, below the fold. Shape and state legend should sit on
   the canvas.
8. The canvas fits the first screen (fixed in `465c3b9`), but on 390×844 it is a 330 px square with
   unreadable 6 px labels.
9. Literal colours in `v3.css` (`#10121d`, `#565c77`…), an unresolved `--muted`, and 7 px radii
   diverge from the Cortex tokens.
10. Show Cypher is a plain `<details>` with raw JSON and unhighlighted Cypher.

Already correct and preserved: hypothetical captions and inspector status (`G_DEDUPE\nbroken`),
verdict above the canvas, names for reviewers and person nodes.

### Landing (`/`)
1. The first screen states "What still holds?" without the product's hook; a first-time judge does
   not learn what Premise does in one sentence.
2. Four scenario chips compete with each other; there is no single primary action.
3. The stat row mixes a revision number, a SHA and counts; it does not surface what matters
   (healthy guarantees, promises expiring, orphaned decisions).
4. The HUD repeats counts and asks the visitor to fire a change, competing with the chips.
5. The brain is strong and stays; its idle motion is already subtle.

### Benchmark (`/benchmark`)
1. No headline number: a judge must read a bar chart and a 21-row table to learn that the graph's
   F1 is 0.79 against 0.30 for the best retriever.
2. Bars appear statically; colour alone separates systems.
3. The record line shows a raw ISO timestamp with microseconds.
4. The 21-row table dominates the page; the caveats sit below it at the same weight as the result.
5. The "Show recorded Cypher" drawer is a bare summary row.

### Continuity (`/continuity`)
1. The person picker is a plain select; the departure is the interaction and should be one tap.
2. Four equal text boxes with large display headings; numbers are buried in sentences.
3. The connection graph is a uniform lavender cluster with a faint red node; nothing shows which
   connections the departure cuts.
4. Bridge score prints unrounded (`69.1666666666667`).
5. The canvas height is an inline style; no empty or loading state for the graph.

### Time machine
1. Hidden inside the Explorer disclosure; on the landing page it floats above the guarantee board.
2. The slider changes the date on every step with a request per step; nothing explains *why*
   G_DEDUPE turns amber (Anika Rao's attestation on A_STABLE_EVENT_ID needed review by 2027-03-01).
3. Marks are an unstyled datalist; the expiry is not visible on the track.

### Show Cypher
1. Raw JSON parameters and plain Cypher; no syntax colour, no timing comparison.
2. "Copy Cypher" gives no state feedback beyond swapping text; failure copy is long.

### What if, Assessment, Entity
1. Consistent with Cortex already; they use the shared sheet.
2. Assessment "Who should review" and Entity "Current reviewers"/"Reviewer evidence" print person
   ids (`p_anika`, `p_jun`) — the brief requires names everywhere.
3. Attestation evidence shows "Anika Rao (p_anika)"; the id is noise for a reader.

## Plan

1. **Tokens.** One `tokens.css` (colour with accessible state pairs, spacing, radius, type scale,
   elevation, motion durations/easings), imported by the shared sheet so v1, v2 and V3 pages use
   one source. `v3.css` rewritten on tokens.
2. **Explorer.** Toolbar above the stage (search, depth, kinds, time, Play the story); a stage
   frame whose header is the verdict banner (state colour, icon, counts, ARIA live); a layered
   layout (assumptions → guarantees by REQUIRES depth → decisions) so causality reads upward; an
   on-canvas legend; inspector as a side panel on desktop and a sheet after the canvas on mobile.
3. **Propagation.** Visualise the real `/api/check` result: pulse the touched assumption, then
   send a signal along each REQUIRES edge hop by hop (≈220 ms per hop) so guarantees turn red in
   chain order, then light affected decisions, then land the verdict. Apply verified fix heals in
   reverse. Sequences are cancellable; reduced motion applies states instantly with a brief
   highlight.
4. **Story mode.** Ten captioned steps on real API data (works on replay), with pause, previous,
   next, skip and keyboard control.
5. **Landing.** Hook sentence, the brain, three live stat chips, one primary "Play the story".
6. **Benchmark.** Headline result, bars that grow once on first view, quiet caveats, compact table.
7. **Continuity.** Person chips; cut connections highlight; impact cards with counts fill in.
8. **Time machine.** Inline track with attestation marks, spring-following date bubble, throttled
   requests, and an expiry callout naming the person and assumption.
9. **Show Cypher.** Highlighted Cypher and parameters, timing bars, copy with feedback.
10. **Remaining pages.** Names instead of ids; tokens.

## Progress

Updated after each page below.

### 1. Tokens and Explorer — done (this commit)

- `premise/web/static/tokens.css` (copied byte-identical to `premise_v2/web/static/`) is the single source for
  colour (holds/unknown/broken/violated with fields), space, radius, type scale, elevation and motion
  (`--dur-feedback 140ms`, `--dur-state 240ms`, `--dur-hop 220ms`, ease-out/in/in-out). Reduced motion sets every
  duration to 0. `style.css` imports it; `v3.css` was rewritten on tokens only (no literals, no `--muted` gap).
- Explorer: compact toolbar (search, depth, include, time machine) above the stage; on phones depth/include/time
  fold behind an Options toggle. Verdict banner above the canvas is the ARIA live region, coloured by verdict with an
  icon, counts and reviewer names, plus "Apply verified fix". On-canvas shape/state legend. Layered layout
  (facts → assumptions → guarantees by REQUIRES depth → decisions/services) so failure reads bottom-up; row gap adapts
  to the canvas aspect.
- Propagation (`consequences.js`, class `Run`): visualises one real `/api/check` result. The camera frames the
  affected area, the touched assumption pulses, a signal travels each REQUIRES edge (220 ms per hop) and guarantees
  turn red in chain order, affected decisions light up, then the verdict lands. A fix heals in reverse order. Runs
  diff against what the graph currently shows, are cancelled by any newer change, and apply states instantly under
  reduced motion. Every final state comes from the response or the recorded baseline.
- Story mode (`story.js`): "Play the story" runs ten captioned steps on real data (overview → G_DEDUPE → Paylane
  24→72 → propagation → BLOCKED → reviewers → verified fix → heal → 2027-03-02 → Anika Rao's attestation and amber
  G_DEDUPE). Pause/resume (Space), previous/next (arrows), exit (Escape); `?story=1` autostarts. Skipping or going back
  replays earlier steps instantly. Works on the replay site.
- Time machine: track with attestation ticks, spring-following date bubble, debounced requests; in the Explorer the
  verdict banner names the expiring attestation and person.
- Show Cypher: highlighted Cypher, per-query timing bars, row counts, parameters toggle, copy with feedback.
- Names: the verdict and story use names from the API (`names`), not ids.

Verification (actual): `scripts/check_ui.py` passed against a live app on an isolated graph (no page/console
errors; canvas and verdict in the first screen at 1440×900 and 390×844; hypothetical labels; story start to finish
at both sizes; reduced motion at both sizes; Continuity names). `scripts/check_replay.py` passed on a fresh export
(3,333 responses, 8 dates; 211 local requests, zero external; story and reduced motion included). New
`tests/test_showcase_ui.py` (tokens shared, WCAG AA for all text/state colours on four surfaces, Explorer markup
order and ARIA, JS budget) plus the existing web/graph-API/v2-web tests: 35 passed. The full suite and
`premise scenarios` have **not** been run since these changes. After screenshots: `artifacts/ui-after/explore*`.

Known limits: overview labels stay small at 1440 (30 nodes, width-limited); story and checks zoom to the affected
area where labels are readable.

## Original handoff: remaining work before this completion pass

1. **Landing (`/`)** — started: `premise/web/app.py` adds `expiring_attestations(health)` to the brain context
   (active attestations due for review within 180 days; currently A_STABLE_EVENT_ID, Anika Rao, 1 Mar 2027). Still to
   do in `brain.html`: hook "Search finds documents. Premise finds consequences." as the h1; three stat chips (guarantees
   healthy = holds / total; promises expiring soon = `expiring|length`; orphaned decisions = `orphaned|length`); one
   primary CTA "Play the story" → `/explore?story=1`. Keep the 3D brain, keep a heading named "What still holds?"
   (checked by `check_ui.py` and `tests/test_agents_and_web.py`) and the Analyst ("Model provider configured" is tested).
   Move the four fire chips and `#fire-result` out of the hero into the network section (`fire.js` only needs
   `[data-fire]` and `#fire-result`).
2. **Benchmark** — headline number (graph F1 0.789 vs best retriever, vector k=3 0.297), bars that grow once on first
   view (transform `scaleY`, origin bottom; instant under reduced motion), system name + value labels on bars, quieter
   caveats, compact table (test split only by default), readable record date. `check_ui.py` expects 21 rows in
   `#benchmark-rows`.
3. **Continuity** — person chips instead of the select (keep `#departure-person` working for the checkers), impact
   cards with counts that fill in, highlight cut connections in the Cytoscape view, round the bridge score, use names
   everywhere (already for reviewers and person nodes).
4. **What if / Assessment / Entity** — replace remaining person ids with names (Assessment "Who should review",
   attestation "(p_anika)", Entity "Current reviewers" and "Reviewer evidence"). The assessment result has reviewer ids;
   names can be looked up read-only as `graph_api.py` does for node details.
5. **GIF** — record 10–15 s of S1 propagation and the verified-fix heal into `docs/media/propagation.gif` and link it
   from the README (no ffmpeg/ImageMagick here; Pillow can assemble Playwright frames: `pip install --target` a
   scratch dir as done for screenshots).
6. **Finish** — full `pytest`, `premise scenarios` on an isolated graph, both checkers, after screenshots of every page
   into `artifacts/ui-after/` (`scripts/capture_ui.py artifacts/ui-after --base <url> [--pages …]`), then update this file.

How to run what this pass used: `premise --graph premise_showcase ingest && premise --graph premise_showcase demo`,
then `premise --graph premise_showcase serve --web-port 8040` with `POLL_ENABLED=false`; checkers take
`PREMISE_BASE_URL`; replay: `scripts/export_replay.py` then `python -m http.server 8031 --directory site`.

## Remaining showcase pages — implemented

This section supersedes the unfinished page and GIF items above; the audit and earlier verification remain
historical evidence. Page work is in local commit `b09fe50`, and the recording is in `edcd9e8`. Work stays on
`ui/showcase`, under the existing sole author, with no push. Final verification is recorded separately below
when completed; implementation is not a claim that every finish check has passed.

The direction remains an ordinary refinement of Cortex: Persuade for the landing hero, Operate for the
working pages. Near-black surfaces, indigo light, Unbounded display type, Manrope interface text, technical
monospace, the existing MRI brain and glass materials remain the visual authority. This work introduces
no replacement world, composition seed or new design-system rules. `PRODUCT.md` and `docs/DESIGN.md`
were checked against the finished source and preserved; system/sidecar drift is not repaired as a side effect.

- **Landing:** the exact hook is now “Search finds documents. Premise finds consequences.” The brain stays,
  followed by the existing decision-network and guarantee content, including “What still holds?” and the
  Analyst. Three live health statistics show guarantees healthy / total, attestations expiring within 180 days,
  and orphaned decisions. One primary “Play the story” action opens `/explore?story=1`. The four proposed-change
  chips and `#fire-result` move into the network section, preserving the existing fire interaction while
  giving the first viewport one clear action.
- **Benchmark:** the headline comparison comes from the committed benchmark response: test macro F1
  **0.789** for graph reasoning versus **0.297** for the best passage retriever, vector **k=3**. The client
  selects the graph and best retriever from the returned test/all rows rather than hardcoding those scores.
  Bars retain system, k and numeric labels and grow once on first view; reduced motion shows settled values
  immediately. The recording date is readable and explicitly UTC. Authored-label, synthetic-company,
  structural-advantage and pending-human-review caveats stay visible before a collapsed disclosure containing
  all **21 test measurement rows**. The result does not claim general QA superiority.
- **Continuity:** active people have one-tap chips with an explicit pressed state; the original
  `#departure-person` select still works. Three impact sections expose returned counts and a busy state.
  Person nodes use names, and links touching the departing person are dashed red with a written explanation.
  Bridge scores round to at most two decimal places; the text keeps centrality separate from guarantee health.
  Connection loading, empty and error messages are explicit, stale requests are ignored, and errors clear
  previous results instead of leaving a healthy-looking graph. All departures remain hypothetical.
- **Assessment and Entity:** reviewer, unavailable-person, candidate and attestation presentation uses names.
  A read-only person-name helper and template filter resolve display text without mutating graph identities
  or stored assessment ids. The remaining What-if page retains its existing behavior and was included in
  the capture set. A page-scoped assessment heading size/wrapping correction fixes the clipped mobile title.
- **Responsive scope:** landing copy and brain stack below 1100px, with phone sizing below 760px. Landing
  navigation can scroll within its container, preventing page overflow at tablet width. These corrections
  live in `premise/web/static/v3.css`; they do not redefine shared tokens or the base stylesheet.
  The coordinating build pass verified an empty diff against incoming `3cf535c` for both apps' `style.css`
  and `tokens.css`; each pair remains byte-identical.
- **Recording:** [`docs/media/propagation.gif`](media/propagation.gif) shows the real S1 retry-window break
  and verified-fix heal. The artifact is **11.98 seconds, 33 frames, 4,543,211 bytes**; README embeds it and
  links [`scripts/record_propagation.py`](../scripts/record_propagation.py) for reproduction. It was captured
  from the local Explorer and real FalkorDB checks, not fabricated verdicts or a UI-only animation.

Verification available at this documentation handoff: focused web checks **16 passed** and expanded showcase
checks **6 passed**. The initial 18 page/viewport captures reported zero page/console errors and no horizontal
overflow at 1440×900 and 390×844. The final landing capture at 768×1024 has no page overflow or copy/brain
overlap. The final live UI check after the responsive corrections passed with zero page/console errors,
including assessment title fit, tablet landing layout, story playback and reduced motion at both sizes,
and the new page controls. The full suite, isolated scenarios and fresh replay check had not yet run in
this pass. These are the handoff's actual limits, not final finish results.

Evidence: [`artifacts/ui-after/`](../artifacts/ui-after/) contains `landing`, `benchmark`, `continuity`,
`assessment`, `entity` and `whatif` captures at widths 1440 and 390, plus their `-full.png` versions and
`landing-768.png`. The independent fresh reviewer initially identified the clipped mobile assessment title;
the correction verdict scored it resolved with no introduced regressions and disposition **ship**, scoped to
the correction captures.

The raw taste report at `.runtime/showcase-taste/report.json` retains findings about pinned Cortex decoration
and exact headline wraps; its tablet overflow finding was corrected in the build. The Jinja/CSS detector's
unresolved-variable contrast findings assumed a light background and its type-ramp findings remain advisory;
the actual AA state/token checks passed. These findings are recorded as limits, not promoted into new design
rules or used to rewrite the incumbent design record.

## Final verification — 2026-10-17

| Check | Actual final result |
| --- | --- |
| Full `python -m pytest -q` suite | **348 passed**, zero failures/errors/skips; **373.86 seconds** |
| `premise scenarios` | **12/12 passed** on the isolated validation graph |
| `scripts/check_ui.py` | Passed, zero page/console errors; story and reduced motion at desktop/mobile, names, new controls, mobile title fit and tablet landing assertions |
| Fresh `scripts/export_replay.py` | **3,333** real recorded responses across **8** dates |
| `scripts/check_replay.py` | Passed; **208** local requests, **zero external requests**, zero errors; story, reduced motion, benchmark and departure controls |
| After captures | **38 PNGs**, covering **19** page/viewport combinations; zero reported console errors or document overflow |
| Propagation GIF | **11.98 seconds**, **33 frames**, 4,543,211 bytes; real S1 break and engine-verified repair |

The suite emitted 35 warnings because the existing red-team tests' `record_property` metadata
is incompatible with JUnit's default `xunit2` report format. These are reporting warnings;
all tests passed. Logs/JUnit and the copied live/replay reports are under ignored
`.runtime/showcase-validation/`; replay screenshots/report are under `.runtime/v3-replay/`.
The committed captures and their machine-readable results are in
[`artifacts/ui-after/`](../artifacts/ui-after/).

Validation used a uniquely named `premise_showcase_finish_<uuid>` graph and loopback server,
with GitHub polling and model calls disabled. The temporary server and graph were removed
after verification. The pre-existing `premise_showcase` graph and running FalkorDB service
were preserved. Replay export and tests clean up their own graph namespaces.

Local checkpoints: `b09fe50` (page refinements and regressions), `edcd9e8` (GIF and recorder),
`fe57901` (responsive corrections), `7e06d63` (all after captures), followed by this finish
record. Commits use Shaik Mohammad Razeef as the sole author, without co-author trailers.
This pass did not merge into `main`, push, deploy Pages, or record a hackathon submission video.

The known 30-node overview label limitation remains: use the inspector or story focus for
readable detail. The requested exact landing hook wraps to three desktop/four phone lines;
it was retained rather than shortened to satisfy the generic taste meter. Existing Cortex
glass, light and technical typography were preserved as required. Raw detector/taste reports
are not claimed to be clean; their real tablet overflow finding was fixed and other scoped
exceptions remain documented above. The fresh finish reviewer scored the mobile title fix
resolved, with no introduced regressions in the supplied captures; disposition **ship** applies
to that correction review.

## Landing composition correction - 2026-10-17

The supplied screenshot showed the unwanted current composition. Restored the earlier Cortex hero:
large bright PREMISE wordmark above the central MRI brain, with copy at the lower left; tablet and
phone stack the brain before the copy and story action. Removing the showcase layout overrides in
`premise/web/static/v3.css` lets the existing shared `style.css` own this composition. The current
hook, real health statistics, `/explore?story=1` action and interactions remain. This supersedes the
earlier showcase hero composition only; `PRODUCT.md`, `docs/DESIGN.md`, shared styles and tokens
were checked and preserved. UI checkers now expect the restored responsive ordering.

Verification for this correction: `.runtime/check_centered_hero.py` passed against the existing
local app at 1440x900, 768x1024 and 390x844, checking brain readiness, live statistics, story action,
ordering and zero horizontal overflow, with zero console/page errors. Six viewport/full-page
captures are in `.impeccable/review/centered-hero/`; the scoped detector returned `[]` in
`.runtime/centered-hero-detector.json`. `pytest tests/test_showcase_ui.py -q`: **6 passed in 6.87s**.
The full suite and scenarios were not rerun for this CSS correction; their earlier totals remain
historical. Existing system-record drift and decoration exceptions were not canonized or repaired.
The finish review caught text touching the brain; a desktop-only heading measure restored clear
separation. Fresh captures resolved that finding with no regressions: disposition **ship** for
the scored heading-clearance correction.

## Hero spacing and network legibility - 2026-10-17

The follow-up screenshots showed crowded copy/statistics and graph connections lost in the
bright anatomical surface. Kept the large wordmark and central brain, separated health statistics
into a full-width desktop row, and stacked the metrics on phones. The headline has more line
spacing; copy, action and metrics now have distinct groups. Counts and copy remain unchanged.

`brain3d.js` now draws the real network above a softer MRI surface. Connections have a dark
casing and thicker ice-coloured centres; reduced node halos leave lines visible. Hovering or
checking a change further dims the anatomy, retaining the existing red/green path semantics,
tooltips, rotation and pulses. The shared design tokens and other pages were preserved.

Validation: **6 showcase tests passed in 8.46s**. Browser checks at 390x844, 768x1024, 1440x900
and 1920x1080 passed with no horizontal overflow or page/console errors. Checks cover metric
spacing, hover tracing, real S1 `BLOCKED` and verified-fix `CLEAR_WITHIN_SCOPE`; normal motion,
drag rotation and reduced motion were exercised. Captures and the report are under ignored
`.impeccable/review/hero-readability/`. The full suite/scenarios were not rerun for this visual
change. `scripts/showcase_checks.py` retains spacing checks for subsequent live/replay runs.

## Separate health card and story emphasis - 2026-10-17

Moved the live health summary into its own card immediately after the hero, retaining its three
desktop columns and stacked phone rows. The story action is now a 60px gold button with a larger
play icon, stronger type, hover treatment and a visible keyboard focus outline. The story URL,
copy and graph-derived counts remain unchanged.

Brain connections use cyan `--brain-link` (`#47ddec`); travelling signals use gold
`--brain-signal` (`#ffb454`), with a small solid core so movement stays visible against the brain.
The existing red failure and green checked paths retain their meanings. These two colour roles
live in the shared token files; both copies remain identical. No new animation was added to the
story button, and reduced motion still disables the travelling signals.

Validation: **6 showcase tests passed in 6.19s**, including contrast checks for both new colours.
Live browser checks passed at 390x844, 768x1024, 1440x900 and 1920x1080: separate health card,
CTA size/colour/focus, actual click into the story, hover tracing, S1 failure and verified fix,
normal/reduced motion and drag rotation. No horizontal overflow or page/console errors occurred.
Captures and report: `.impeccable/review/hero-action/` (ignored). The full suite and scenarios
were not rerun for this visual change.
