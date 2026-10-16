---
name: Premise
description: A company brain for engineering decisions, drawn the way Cajal drew the brain, in darkfield.
colors:
  ground: "#0f0e0c"
  ground-2: "#161411"
  ground-3: "#1e1b17"
  ground-4: "#2a2620"
  ink: "#ece3cf"
  ink-2: "#c9bfa9"
  ink-3: "#9b917d"
  holds: "#8fcfa6"
  unknown: "#eab65a"
  broken: "#f27a62"
typography:
  display:
    fontFamily: "Bodoni Moda, Didot, Georgia, serif"
    fontSize: "clamp(3.4rem, 6.6vw, 6rem)"
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: "-0.035em"
  page-title:
    fontFamily: "Bodoni Moda, Didot, Georgia, serif"
    fontSize: "clamp(2.9rem, 5.6vw, 5.25rem)"
    fontWeight: 400
    lineHeight: 0.95
    letterSpacing: "-0.03em"
  heading:
    fontFamily: "Bodoni Moda, Didot, Georgia, serif"
    fontSize: "clamp(1.7rem, 2.4vw, 2.15rem)"
    fontWeight: 400
    lineHeight: 1.08
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Schibsted Grotesk, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  data:
    fontFamily: "Schibsted Grotesk, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  code:
    fontFamily: "Geist Mono, Cascadia Mono, Consolas, monospace"
    fontSize: "13.5px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "-0.01em"
rounded:
  base: "3px"
spacing:
  gutter: "clamp(16px, 3vw, 40px)"
  section: "clamp(56px, 7vw, 96px)"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.base}"
    padding: "12px 20px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "#fff8e8"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "9px 14px"
    height: "40px"
  chip-pressed:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "12px 14px"
  panel:
    backgroundColor: "{colors.ground-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
---

# Design System: Premise

## Overview

Premise is an architecture-review workbench whose primary question is whether engineering guarantees
still hold. Its visual world is **neural cartography**: the company's reasoning drawn the way Santiago
Ramón y Cajal drew the brain, as inked cells and the paths signals take between them, shown in
darkfield (paper becomes night, ink becomes light). Cajal's public-domain plates are the imagery; the
company's own decision network, drawn live from FalkorDB, is the signature.

The Brain page opens with a first-time-visitor hero (headline, one sentence, live readout, "fire a
change" scenarios) beside **Fig. 1**, the live plate. Everything below the hero, and every other page,
is an operating surface: familiar tables, forms and navigation, with the world entering only through
palette, type, the plates and one signature move.

The signature move is **firing**: a signal travelling along an inked path wherever a consequence chain
is shown. It runs in the hero plate (ambient impulses, and the broken path after a fired scenario) and in
the Mermaid dependency graphs on the assessment and What-if pages.

## Colors

A restrained darkfield: one warm ink-black ground stepped in tone, one paper-cream ink, and three state
colours that only ever carry meaning.

### Neutral
- **Ground** `#0f0e0c`: the page. Warm, never pure black.
- **Ground 2–4** `#161411`, `#1e1b17`, `#2a2620`: tone steps for panels, tables, hover and tooltips.
  Surfaces are separated by tone, not by borders or shadows.
- **Ink** `#ece3cf`: all running text and drawn lines; also the primary button fill.
- **Ink 2** `#c9bfa9` for secondary text, **Ink 3** `#9b917d` for notes and table headers.

### State
- **Holds** `#8fcfa6` (sage), **Unknown** `#eab65a` (amber), **Broken** `#f27a62` (vermilion), each with a
  ~12% field for badge backgrounds. Mermaid graphs receive matching `classDef`s from the server.

### Named Rules
- **Colour travels with a word and a glyph.** Every state badge renders a Lucide glyph (check,
  circle-help, octagon-x) and the state word; colour is never the only signal.
- **Unknown is never green.** Unverified, unevaluable and needs-review all take the amber state.

## Typography

- **Bodoni Moda** sets the voice: page questions ("What still holds?", "Consequences, connected."),
  section headings, figure numbers ("Fig. 1."), and the closing wordmark.
- **Schibsted Grotesk** carries the interface: body, tables, controls, captions.
- **Geist Mono** appears only inside `<code>`: identifiers (G_DEDUPE, ADR-012, fact keys), predicates,
  file positions and commands.

### Hierarchy
Display 6rem max (hero), page titles to 5.25rem capped at 11ch so they never cross a plate, section
headings ~2.15rem, body 16px, data and captions 15px, notes 13px. Headlines stay within two lines.

## Layout

Max width 1440px with fluid gutters (16–40px). Brain: hero 5/7 split, full-bleed Fig. 2 strip, board
(guarantee table + 380px sticky Analyst), lower grid (recent assessments + accountability gaps). What-if:
proposal (presets + facts table) left, sticky "Predicted impact" panel right. Under 1100px everything
stacks; under 760px the Brain and fact tables become stacked rows with labelled cells, so no task needs
sideways scrolling.

## Elevation & Depth

Flat. Depth comes from tone steps between ground levels. The only shadow is on the plate tooltip, the
one thing that truly floats.

## Shapes

A single 3px radius for panels, tables, buttons, chips, inputs and badges. Plates are unframed: cream
ink on transparency, sitting directly on the ground.

## Components

### Buttons
Primary: cream fill, ink-black text, 46px tall, icon + label, `scale(0.97)` on press.

### Chips
Scenario presets: outlined, amber zap glyph; `aria-pressed="true"` inverts to cream with a vermilion glyph.

### Inputs / Fields
Ink-black field, 1px cream-alpha border, amber caret; a filled fact input turns amber to show a pending
proposal.

### Navigation
Plain bar: wordmark with the pyramidal-cell mark, four icon links, current page on a tone step,
fictional-company label at right.

### Specimen plate (signature)
`static/plate.js` draws facts → assumptions → guarantees from `/api/health` data as boutons, round
somas and pyramidal somas joined by curved axons, coloured by live health. Pointing or focusing traces a
cell's connections with a tooltip; guarantee cells are keyboard links. "Fire a change" posts a scenario to
the read-only `/api/check` and fires the broken path in vermilion, re-checked paths in sage.

### Plates and figures
Every Cajal plate is processed to cream ink on transparency (`static/img/plate-*.webp`) and captioned
"Fig. n." with its source. Credits sit in the footer.

## Do's and Don'ts

### Do:
- Show every state with its evidence and its path.
- Put identifiers in `<code>`; keep mono out of prose.
- Use plates only where they sit clear of text; cap headline measure instead of moving the plate behind it.
- Give motion a reduced-motion path; firing and ambient impulses stop when reduced motion is requested.

### Don't:
- Invent counts, scores or progress; every number on screen comes from the graph.
- Add eyebrows above headings, gradients, glass, or glows.
- Animate keyboard-driven or high-frequency actions; feedback stays under 250ms.

### Image credits
Drawings by Santiago Ramón y Cajal via Wikimedia Commons, public domain: nerve cells in the brain,
hippocampus (modified), Purkinje cells, cortex drawings, mammalian retina (1901). Cerebral cortex in a
child: Wellcome Collection, CC BY 4.0. Icons: Lucide 0.460.0, ISC.
