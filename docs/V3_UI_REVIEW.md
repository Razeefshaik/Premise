# V3 UI review record

This is an ordinary extension of Premise's existing Cortex Operate/Read interface. It does not replace or amend the design system in `docs/DESIGN.md`.

The extension retains the near-black field, Unbounded headings, Manrope interface text and JetBrains Mono technical text supplied by `premise/web/static/style.css`. Decision Explorer uses a real graph beside a quiet Evidence / What if inspector, stacked below 900px. Benchmark presents recorded results and their limits; Continuity labels departure analysis hypothetical. Health remains mint for holds, red for broken and amber for unknown, accompanied by written states. The time controls explicitly forecast attestation expiry from the current graph rather than reconstructing old revisions. Replay limits are visible; benchmark status uses the returned recording timestamp.

The finish reviewer reported **ship** after scoring three listed fixes resolved: the visible Test macro F1 heading, a horizontally scrollable chart with an 820px minimum SVG width, and the ASCII replay phrase `depths 1 to 3`. That disposition applies to those fixes. It does not certify backend correctness or every possible UI state. The supplied final review captures are `.impeccable/review/v3/{explore,benchmark,continuity}-{1440,390}.png`; this documentation pass checked their presence without repeating browser review or tests.

Source checked: `PRODUCT.md`, `docs/DESIGN.md`, `premise/web/static/style.css`, `v3.css`, `explore.js`, `benchmark.js`, `continuity.js`, `time.js`, `source.js`, and the `base.html`, `explore.html`, `benchmark.html`, `continuity.html`, `_time.html` templates. The existing v1 and v2 shared stylesheets have matching hashes.

The existing detector output, `.runtime/v3-detector.json`, contains advisory palette, radius and type-ramp differences. Its static CSS/Jinja resolution limits are not runtime proof. No second detector run was performed for this record.

The new extension's literal control/surface values and unresolved `--muted` reference are not promoted into shared tokens or system rules. Separately, the older design record predates these v3 surfaces and has no `.impeccable/design.json` sidecar; those existing documentation gaps are preserved rather than repaired or treated as authorization for a system refresh.
