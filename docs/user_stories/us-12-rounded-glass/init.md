> **ID:** US-12
> **Status:** DONE
> **Specs:** [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md), [brand book §1](../../brand-book/init.md)

## Overview

[US-11](../us-11-glass-circle/init.md) made the thumb a circle and left the labels on top of it. The circle is smaller than `System`, and a label above the glass does not refract. This story makes the thumb one rounded square the width of the selected word, with the labels under the glass.

Task: [thumb](tasks/task-01-thumb.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | One `Glass`. Rounded square, radius 12px, height `2.25rem`, width follows the segment. | A circle, a sharp square, or three glasses |
| D2 | Labels sit under the glass. The glass does not take pointer events. Optics are [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md). | Labels as children of `Glass` |
| D3 | Segments stay square. | Rounding the page |

## Goals

- Cover the selected word with one rounded glass.
- Leave the letters readable, and bent at the rim.

## Non-goals

- A second theme control.
- Rounding segments, buttons, or panels.
- The theme reveal circle.

## User Story

**As** a person changing the theme, I want the active word under a rounded glass, so the whole label sits in the lens and the rim bends the letters.

**Acceptance**

- The control stays one radiogroup named `Theme`, with the same three labels.
- One `Glass` is mounted. Choosing a label translates it and sets its width to that segment. The corner radius is 12px.
- The labels are behind the glass. Clicks still hit the radios.
- Without `backdrop-filter`, the thumb is `--ink` and the selected label is `--paper`.

## Definition of Done

- [x] `npm test` and `npm run build` pass in both React pages. The resume page’s initial JS is 89.3 KB gzipped.
- [x] [brand book §1](../../brand-book/init.md) describes the rounded square and links [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md).
