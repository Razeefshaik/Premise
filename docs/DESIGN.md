---
name: Premise
description: A company brain for engineering decisions, drawn as a living cortex.
colors:
  bg: "#030305"
  frame: "#090a12"
  panel-solid: "#0e1019"
  ink: "#f2f4ff"
  ink-2: "#b9bfda"
  ink-3: "#8a90ad"
  indigo: "#5b63ff"
  indigo-2: "#8b92ff"
  ice: "#dfe4ff"
  holds: "#7cf0c8"
  unknown: "#ffd27a"
  broken: "#ff6b8b"
typography:
  wordmark:
    fontFamily: "Unbounded, Segoe UI, sans-serif"
    fontSize: "clamp(64px, 12.6vw, 200px)"
    fontWeight: 800
    lineHeight: 0.86
    letterSpacing: "-0.05em"
  heading:
    fontFamily: "Unbounded, Segoe UI, sans-serif"
    fontSize: "clamp(2.4rem, 5vw, 4.6rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.04em"
  body:
    fontFamily: "Manrope, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  code:
    fontFamily: "JetBrains Mono, Consolas, monospace"
    fontSize: "13.5px"
    fontWeight: 500
rounded:
  frame: "28px"
  card: "22px"
  control: "12px"
  pill: "999px"
components:
  button-primary:
    backgroundColor: "#ffffff"
    textColor: "#0b0c14"
    rounded: "{rounded.control}"
    padding: "12px 20px"
    height: "46px"
  chip:
    backgroundColor: "rgb(150 160 230 / 0.07)"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "9px 15px"
  card:
    backgroundColor: "rgb(150 160 230 / 0.07)"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "24px"
---

# Design System: Premise · Cortex

## Overview

Premise is a company brain, so the interface is one. The Brain page opens on a framed hero lit by an
indigo glow: the PREMISE wordmark, and below it a real MRI-derived brain drawn as a hologram (a fresnel
shell, a twinkling point cloud of its surface, and a scan line sweeping through it). Threaded inside the
brain is Premise's live decision network as nerves: facts deep, assumptions in the middle, guarantees
toward the cortex, coloured by current health. Signals travel along real fact → assumption → guarantee
paths. The same network appears flat as the 2D nerve plate (Fig. 1) further down the page.

"Fire a change" is the signature interaction. A scenario is posted to the read-only `/api/check`; the HUD
reports the verdict, the broken path burns red in the 3D brain and the 2D plate, signals race along it, and
the affected guarantee cards pulse. One event (`premise:fire`) drives all three views.

The same system covers both apps: the v1 brain (Brain, Assessment, What-if, Entity, Error) and the v2
evidence review queue. `premise/web/static/style.css` and `premise_v2/web/static/style.css` are identical,
byte for byte, and a test asserts it. The v2 app's Content-Security-Policy is self-only, so fonts are
self-hosted in both apps' `static/fonts/`.

## Colors

Near-black ground (`#030305`), framed panels (`#090a12`), frosted glass surfaces (indigo-tinted white at
7–12%), ink `#f2f4ff` with two quieter steps. Indigo `#5b63ff` / `#8b92ff` is the light the interface
lives in; ice `#dfe4ff` draws the brain and identifiers. State colours carry meaning only: holds
`#7cf0c8`, unknown `#ffd27a`, broken `#ff6b8b`, each with a soft glow. Colour always travels with a word
and a Lucide glyph.

## Typography

Unbounded (extended, heavy) for the wordmark, page questions and section headings; Manrope for the
interface; JetBrains Mono only inside `<code>` for identifiers, predicates and commands.

## Layout

Max width 1480px with fluid gutters. A floating glass header bar (pill) on every page. Brain: hero frame
(wordmark, 3D brain right of centre, copy and fire chips bottom-left, HUD bottom-right), network section
(2D plate + legend), guarantee bento (lead card 2×2 with its prerequisites), recent assessments beside the
sticky Analyst, accountability gaps. What-if: proposal left, sticky impact panel right. Below 1100px
everything stacks; below 760px tables become labelled stacked rows.

## Elevation & Depth

Glass panels sit on the ground with an inset hairline, a bright top edge and a deep soft shadow. Cards rise
6px on hover and a radial indigo light follows the pointer across them. A fired guarantee card pulses red.

## Shapes

Frames 28px, cards 22px, controls 12px, chips and the header are pills.

## Components

- **Primary button:** metallic white gradient, ink-black text, indigo bloom, scale(0.97) on press.
- **Chip:** glass pill; pressed state inverts to metallic white with a red zap.
- **State badge:** pill with glyph and word on a 10% tint of its state colour, softly glowing.
- **Hologram brain** (`brain3d.js`): drag to rotate (OrbitControls, no zoom hijack), hover a node for a
  tooltip and its traced connections, click to open the entity. Auto-rotates when idle; pauses offscreen.
- **2D nerve plate** (`plate.js`): the same graph flat, with tracing and firing.

## Motion

Entrance: the brain develops from transparent while the camera eases in; headline and copy rise with
blur; sections reveal as they enter; numbers count up. Ambient: wordmark sheen, point-cloud twinkle,
scan line, travelling signals. Feedback: press scale, card lift and spotlight, chip glow. Navigation uses
cross-document view transitions. Reduced motion and automation get the settled page: no auto-rotate, no
signals, no entrances.

## Do's and Don'ts

- Do show every state with its evidence and its path; numbers come from the graph.
- Do keep both stylesheets identical; change one, copy to the other.
- Don't load external fonts, scripts or styles in the v2 app (CSP).
- Don't invent counts, customers or scores.

### Credits
Brain model: "3D model of brain" by Nevit Dilmen, from MRI, via the NIH 3D Print Exchange and Wikimedia
Commons, CC BY-SA 3.0, repacked to `static/models/brain.bin`. Fonts: Unbounded, Manrope, JetBrains Mono
(SIL Open Font License). Icons: Lucide 0.460.0 (ISC). Three.js 0.160.0 from jsDelivr.
