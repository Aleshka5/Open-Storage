> **ID:** US-10
> **Status:** DONE
> **Specs:** [ADR-0004](../../../adrs/4-theme-thumb-is-liquid-glass.md), [brand book §1](../../brand-book/init.md), [US-04](../us-04-liquid-glass-theme/init.md), [US-09](../us-09-storage-theme/init.md)

## Overview

The theme control is three radios and one sliding thumb. The thumb is a CSS `backdrop-filter`. This story makes that thumb a `Glass` from `@samasante/liquid-glass`, on every React page that renders the control. The states, the key, the labels, the square corners, and the circle reveal stay.

Tasks: [thumb](tasks/task-01-thumb.md), [checks](tasks/task-02-checks.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The thumb is `Glass` from `@samasante/liquid-glass`. Optics live in [ADR-0004](../../../adrs/4-theme-thumb-is-liquid-glass.md). | The CSS blur, edge, and hairline |
| D2 | The control stays one radiogroup named `Theme`, labels `light`, `Dark`, and `System`. The thumb still translates with `transform` over `--dur`. | A popover, a native `<select>`, or three separate lenses |
| D3 | Corners stay square (`radius` 0). No drop shadow. | The rounded demos in the library |
| D4 | The package is a dependency of the storage SPA and of the resume page. The resume page loads it outside the initial chunk so the 95 KB shell budget holds. No other page gets it. | A shared UI package, a script tag on the Keycloak theme, or raising the budget |
| D5 | `theme.preference`, both palettes, and the circle from [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md) stay. | A new key or a refractive rim on the circle |

## Goals

- Slide one liquid-glass thumb between the three theme states.
- Keep the same choice, the same keyboard path, and the same circle.

## Non-goals

- The Keycloak `filenkov` login theme.
- Rounding the control or any other corner.
- A refraction filter on the circle.
- A second theme store.

## User Story

**As** a person changing the theme, I want the active state to be a liquid-glass thumb, so the three choices still read as one control and the selected one is glass.

**Acceptance**

- The header’s right slot keeps one radiogroup named `Theme`, with labels `light`, `Dark`, and `System`. Arrow keys move inside it. At 620px the control stays.
- The selected segment is one `Glass` thumb. It translates with `transform` over `--dur` and its width follows the segment. Its corners are square. It has no drop shadow.
- Choosing a segment writes `theme.preference`, paints the resolved theme, and plays the circle when that circle applies.
- `prefers-reduced-motion: reduce` jumps the thumb. A browser without `backdrop-filter` shows the solid `--ink` face and a `--paper` label on the selected segment.
- The storage SPA and the resume page use the same thumb.

## Definition of Done

- [x] `npm test` passes in `src/open-storage/spa` and in `src/auth-gateway/resume-page`.
- [x] `npm run build` passes in both. The resume page’s initial JS is 89.2 KB gzipped, inside the 95 KB budget.
- [x] [brand book §1](../../brand-book/init.md) describes this thumb and links [ADR-0004](../../../adrs/4-theme-thumb-is-liquid-glass.md). It does not copy the optics.
- [x] [spa/init.md](../../open-storage/spa/init.md) and [resume-page design](../../auth-gateway/frontend/design.md) link that ADR in one sentence each.
