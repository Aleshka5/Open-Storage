> **ID:** US-11
> **Status:** DONE
> **Specs:** [ADR-0005](../../../adrs/5-glass-thumb-is-a-circle.md), [ADR-0004](../../../adrs/4-theme-thumb-is-liquid-glass.md), [brand book §1](../../brand-book/init.md)

## Overview

[US-10](../us-10-liquid-glass-selector/init.md) put `Glass` on the theme thumb and left it a square the width of the selected label. On a flat header that square reads as the label’s own background, and the rim is too thin to see. This story makes the thumb one circle that slides between the three labels.

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | One `Glass`. It is a circle centered on the selected label. Width stays `2.25rem`. | Three glasses, or a square that grows to the label |
| D2 | The rim is thick enough to read on a flat header. Optics are [ADR-0005](../../../adrs/5-glass-thumb-is-a-circle.md). Tint is `--paper-raised` at 18%. | The thin default rim and the 55% plate |
| D3 | Other corners stay square. The circle is the glass exception. | Rounding the page |

## Goals

- Show one glass circle moving between `light`, `Dark`, and `System`.
- Make the edge visible on both palettes.

## Non-goals

- A second theme control.
- Rounding segments, buttons, or panels.

## User Story

**As** a person changing the theme, I want one glass circle on the active choice, so I can see a single object move and I can see that it is glass.

**Acceptance**

- The control stays one radiogroup named `Theme`, with the same three labels.
- One `Glass` is mounted. Choosing a label translates that circle. It does not change width.
- The circle’s corners are fully round. The rim is visible on the light header and on the dark header.
- `theme.preference` and the reveal circle stay as they are.

## Definition of Done

- [x] `npm test` and `npm run build` pass in both React pages. The resume page’s initial JS is 89.3 KB gzipped.
- [x] [brand book §1](../../brand-book/init.md) describes the circle and links [ADR-0005](../../../adrs/5-glass-thumb-is-a-circle.md).
