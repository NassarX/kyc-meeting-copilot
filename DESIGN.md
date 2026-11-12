---
# gstack: design-md-format=spec
name: kyc-presubmit demo viewer
description: 'A case file on a reviewer''s desk: quiet paper, document-like evidence, one marker colour that always means "these are the words".'
colors:
  paper: "#F5F6F3"
  surface: "#FFFFFF"
  text: "#17212B"
  text-muted: "#5B6670"
  text-faint: "#8A949C"
  rule: "#E2E5DF"
  primary: "#0E6B66"
  on-primary: "#FFFFFF"
  primary-soft: "#E6F0EF"
  marker: "#F3DE8A"
  flag: "#A33A1C"
  confirm: "#8A6100"
  gap: "#4C5A66"
typography:
  transcript:
    fontFamily: Source Serif 4
    fontWeight: 400
    fontSize: 1.125rem
    lineHeight: 1.75
  display:
    fontFamily: Source Sans 3
    fontWeight: 600
    fontSize: 1.75rem
    letterSpacing: -0.015em
  body:
    fontFamily: Source Sans 3
    fontSize: 1rem
    lineHeight: 1.5
  label:
    fontFamily: Source Sans 3
    fontWeight: 600
    fontSize: 0.75rem
    letterSpacing: 0.06em
  mono:
    fontFamily: JetBrains Mono
    fontSize: 0.875rem
    fontFeature: tnum
rounded:
  sm: 4px
  md: 8px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  segmented-control:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.md}"
  fact-row-selected:
    backgroundColor: "{colors.primary-soft}"
    rounded: "{rounded.sm}"
  quote-selected:
    backgroundColor: "{colors.marker}"
---

# kyc-presubmit demo viewer

## Overview

**Creative North Star:** a case file on a reviewer's desk. The transcript is the evidence and reads like a record; the check beside it reads like a ledger. Every fact shows its words.
**Product context:** a pre-submission KYC check for private-bank relationship managers. Demo for RMs and compliance officers in interviews; synthetic data only. A local web app opened in Safari on an iPad (landscape, touch) and on desktop.
**Mode per surface:** transcript pane, Read; check pane, Operate; input panel, Operate.
**Reference sites:** none (designed from design knowledge, research declined).
**Key characteristics:**
- Quiet at rest: cited words carry only a faint dotted underline until selected.
- One thing at a time on the right: Overview (flags and items to confirm), Facts, Gaps.
- Tap a fact and its words are marked in the transcript; tap the words and their facts light up.
- A permanent, plain "Synthetic demo data" note.

## Colors

**Strategy:** Restrained. Neutral paper and ink; deep teal is the only interactive colour; the marker yellow is reserved for "these are the words"; red, amber and slate mark flags, items to confirm and gaps, always as small dots or text, never as filled blocks.
**Light or dark:** light, from the use scene: an iPad in a daylit meeting room. A dark variant exists for desktop use and keeps the same roles (teal lightened, marker darkened so ink stays readable on it).

## Typography

Two registers make provenance visible before anyone taps: Source Serif 4 for the transcript (a record), Source Sans 3 for everything the system says (analysis). JetBrains Mono with tabular figures for amounts, dates, percentages, counts and rule IDs. All three are OFL-1.1 from the google/fonts repository (verified 8 Nov 2026 via Fontsource metadata), self-hosted in the viewer so it works offline on a local network. Headings sit at least two steps above body; labels are small caps-style uppercase with tracking.

## Layout

Two panes: transcript on the left (reading measure, max about 760px), the check on the right (440px, white surface, separated by a rule). Below 980px the panes stack. Top bar: brand, demo note, one "New meeting" button. 8px base spacing; touch targets at least 44px; generous vertical rhythm in the transcript (line height 1.75).

## Elevation & Depth

Flat by default: rules and the white check pane do the separating. One shadow only, on the "New meeting" panel (offset 12px, soft blur), because it floats.

## Shapes

Radii 4px (selection, small surfaces) and 8px (buttons, panel, segmented control). No pills except status dots (full).

## Components

- **New meeting panel:** four choices (Record, Upload audio, Paste a transcript, Load the sample case), each with a one-line hint. Opens with a 160ms fade and drop.
- **Segmented control:** Overview, Facts, Gaps with mono counts; a sliding pill marks the active view.
- **Rows:** one language for flags, items to confirm and gaps: a coloured dot, a bold line, a muted second line. Items to confirm are tappable and select their facts.
- **Fact groups:** Identity, People present, Source of wealth, Assets, Structures, Income, Liabilities, Public functions, Planned funding; folding, first group open. A fact row shows its label and its value (mono), plus "Needs confirmation" when contradicted or doubted.
- **Quotes:** dotted underline at rest; on selection a marker sweep fills behind the words.
- States: hover tints, a 3px teal focus ring on everything focusable, honest empty states ("No flags", "Nothing to confirm").

## Do's and Don'ts

- Do keep the marker colour for quotes only.
- Do show the speaker or turn number only when it adds something (hidden when the speaker is unknown).
- Do show readable values ("Business sale", "2022-09"), never raw enum names.
- Do keep the "Synthetic demo data" note visible on every screen.
- Don't use cards, nested cards, or filled coloured blocks for flags.
- Don't add a second accent colour, gradients or glows.
- Don't put every action in the top bar; inputs live in the New meeting panel.

## Motion

- **Approach:** intentional: motion explains what the system is doing.
- **Easing:** enter cubic-bezier(.2,.7,.2,1); move cubic-bezier(.6,0,.3,1).
- **Duration:** micro 120ms, short 160-260ms, medium 380ms.
- **The one authored moment:** the marker sweep behind the quoted words when a fact is selected, then the transcript scrolls to it.
- Also: the Transcribing, Extracting, Checking sequence while a meeting runs; results settle in with a short stagger; folding groups; the sliding segment pill. All of it is off under prefers-reduced-motion.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-11-08 | Initial design system created | Created with design-consultation from the product context; memorable thing: "every fact shows its words". |
| 2026-11-08 | v2: quieter screen, more motion | Review found v1 busy: moved to one input button, a segmented right pane, rows instead of filled blocks, a quiet transcript, and motion that explains processing. |
