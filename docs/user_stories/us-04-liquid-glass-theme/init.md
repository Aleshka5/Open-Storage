> **ID:** US-04
> **Status:** DONE
> **Specs:** [brand book §1](../../brand-book/init.md), [brand book §3](../../brand-book/init.md), [resume-page design](../../auth-gateway/frontend/design.md)

## Overview

The resume page stores `theme.preference`, paints both palettes, and shows a `Theme` radiogroup (`light`, `Dark`, `System`). Selection is the sliding glass thumb in [brand book §1](../../brand-book/init.md). A new resolved theme reveals as a circle that starts at the control. The circle’s edge refracts like the rim of one glass disk. Inside the disk the new theme is unfiltered. Tasks: [decision](tasks/task-01-rim-decision.md), [thumb](tasks/task-02-glass-thumb.md), [circle](tasks/task-03-circle.md), [rim](tasks/task-04-rim.md), [checks](tasks/task-05-checks.md). The rim decision is [ADR-0011](../../auth-gateway/adrs/11-theme-reveal-rim.md).

## Locked decisions

| # | Decision |
|---|---|
| D1 | Storage, resolution, first paint, labels, square corners, and the header slot stay as [US-03](../us-03-page-brand/init.md) and the brand book left them. This story does not add a second store. |
| D2 | Selection is one thumb. It translates with `transform` over `--dur`. Unselected segments stay transparent, label `--ink`, hover fill `--chip`. |
| D3 | The thumb is the only glass that stays on the page. Fill is `--paper-raised` at 55% opacity. `backdrop-filter: blur(14px) saturate(1.7)`. A 1px translucent edge and a 1px inset top hairline. No drop shadow. `will-change: transform` only while the thumb moves. Without `backdrop-filter`, the thumb keeps today’s face: fill `--ink`, label `--paper`. |
| D4 | The circle runs only when a user choice resolves to the other theme. Its center is the theme control’s border box. It grows from 0 until it covers the farthest viewport corner. Inside is the new theme. Outside is the old theme. The mask is `document.startViewTransition`, with `clip-path: circle()` on `::view-transition-new(root)`. No second copy of the page. |
| D5 | The rim refracts as the edge of a solid glass disk. The shift is strongest on the perimeter and falls off across one band 36px wide. The band does not grow with the radius. Displacement is radial, at most 12px, from one SVG `feDisplacementMap` on that band only. The band uses the thumb’s glass read: saturate 1.7 and a 1px specular hairline. No drop shadow, no `feTurbulence`, no WebGL, no filter on the disk interior. The filter is removed when the reveal ends. |
| D6 | `--dur-theme` is `700ms` with `--ease`. The rim uses that same duration and the same center and radius as the mask. `prefers-reduced-motion: reduce` sets `--dur-theme` to `1ms`, skips the view transition, draws no rim, and jumps the thumb. A missing `startViewTransition` applies the theme in the same turn and draws no rim. First paint, a same-theme choice, and an OS change while the preference is `system` do not wipe. A second click waits until the running transition finishes. |

## Goals

- Slide one glass thumb between the three theme segments.
- Reveal a flipped theme through a circle that starts at the control and fills the viewport.
- Bend the seam like the rim of one glass disk, and leave the new theme inside unfiltered.

## Non-goals

- The Keycloak `filenkov` login theme.
- Rounding the control or any other corner.
- A refraction filter on the interior of the circle, or one left on the page after the reveal.
- Changing label casing, the preference key, or the palettes.

## User Story

**As** a visitor, I want the active theme to be a glass thumb that slides, and a theme change to spread from that control as a glass disk, so the new palette arrives through a refracting edge.

**Acceptance**

- The control stays one radiogroup named `Theme`, with labels `light`, `Dark`, and `System`. Arrow keys still move inside it. At 620px it stays.
- The glass thumb slides between the segments. It is the only glass that remains after the reveal. A browser without `backdrop-filter` shows the solid `--ink` face.
- A user choice that flips the resolved theme plays one circle from the control. The new theme is the mask. The old theme stays outside the circle until the circle covers the viewport.
- The boundary refracts across a 36px band. Displacement stays on that band and is at most 12px. The new theme inside the band is not filtered. When the circle finishes, the filter is gone.
- A user choice that does not flip the resolved theme, an OS change under `system`, reduced motion, and a browser without `startViewTransition` change the theme with no circle and no rim.
- `theme.preference` remains the only theme key in `localStorage`.

## Definition of Done

- [x] `npm test` covers the reduced-motion skip and the same-theme skip, and passes.
- [x] The acceptance items above hold on the resume page.
- [x] [brand book](../../brand-book/init.md) §1 describes the sliding glass thumb and the solid fallback. §3 lists the radial reveal, the refractive rim, and `--dur-theme`. Square corners, no drop shadow, and the rest of “anything else is still” stay.
- [x] An ADR in `docs/auth-gateway/adrs/` rejects a refraction filter on the disk interior and on the page after the reveal. It accepts the rim band, points at the brand book for the look, and is written before the page code, in the same change.
