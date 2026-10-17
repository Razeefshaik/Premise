# UI refinement for the showcase

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
