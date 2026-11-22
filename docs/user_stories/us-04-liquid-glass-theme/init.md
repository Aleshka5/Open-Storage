> **ID:** US-04
> **Status:** DONE
> **Specs:** [brand book §1](../../brand-book/init.md), [brand book §3](../../brand-book/init.md), [resume-page design](../../auth-gateway/frontend/design.md)

## Overview

The resume page stores `theme.preference`, paints both palettes, and shows a `Theme` radiogroup (`light`, `Dark`, `System`). Selection is the sliding glass thumb in [brand book §1](../../brand-book/init.md). A new resolved theme reveals as a circle that starts at the control, with a hard-edged boundary. The refractive rim is withdrawn: [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md). Tasks: [decision](tasks/task-01-rim-decision.md), [thumb](tasks/task-02-glass-thumb.md), [circle](tasks/task-03-circle.md), [rim](tasks/task-04-rim.md), [checks](tasks/task-05-checks.md).

## Locked decisions

| # | Decision |
|---|---|
| D1 | Storage, resolution, first paint, labels, square corners, and the header slot stay as [US-03](../us-03-page-brand/init.md) and the brand book left them. This story does not add a second store. |
| D2 | Selection is one thumb. It translates with `transform` over `--dur`. Unselected segments stay transparent, label `--ink`, hover fill `--chip`. |
| D3 | The thumb is the only glass that stays on the page. Fill is `--paper-raised` at 55% opacity. `backdrop-filter: blur(14px) saturate(1.7)`. A 1px translucent edge and a 1px inset top hairline. No drop shadow. `will-change: transform` only while the thumb moves. Without `backdrop-filter`, the thumb keeps today’s face: fill `--ink`, label `--paper`. |
| D4 | The circle runs only when a user choice resolves to the other theme. Its center is the theme control’s border box. It grows from 0 until it covers the farthest viewport corner. Inside is the new theme. Outside is the old theme. The mask is `document.startViewTransition`, with `clip-path: circle()` on `::view-transition-new(root)`. No second copy of the page. |
| D5 | The circle’s edge is a hard cut. There is no rim, no `feDisplacementMap`, no saturate and no hairline. [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md) withdraws the rim because it does not read at the resume page’s size, and it costs a per-frame viewport canvas. The sliding thumb keeps its glass read. |
| D6 | `--dur-theme` is `700ms` with `--ease`. The circle uses the same center and radius as the mask. `prefers-reduced-motion: reduce` sets `--dur-theme` to `1ms`, skips the view transition, and jumps the thumb. A missing `startViewTransition` applies the theme in the same turn. First paint, a same-theme choice, and an OS change while the preference is `system` do not wipe. A second click waits until the running transition finishes. |

## Goals

- Slide one glass thumb between the three theme segments.
- Reveal a flipped theme through a circle that starts at the control and fills the viewport.

## Non-goals

- The Keycloak `filenkov` login theme.
- Rounding the control or any other corner.
- A refraction filter on the circle’s edge, its interior, or the page after the reveal. The rim is withdrawn by [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md).
- Changing label casing, the preference key, or the palettes.

## User Story

**As** a visitor, I want the active theme to be a glass thumb that slides, and a theme change to spread from that control as a circle, so the new palette arrives from the control and fills the screen.

**Acceptance**

- The control stays one radiogroup named `Theme`, with labels `light`, `Dark`, and `System`. Arrow keys still move inside it. At 620px it stays.
- The glass thumb slides between the segments. It is the only glass on the page. A browser without `backdrop-filter` shows the solid `--ink` face.
- A user choice that flips the resolved theme plays one circle from the control. The new theme is the mask. The old theme stays outside the circle until the circle covers the viewport. The edge is a hard cut.
- No SVG filter, displacement, saturation or hairline is drawn at the circle’s edge, and none remains on the page after it.
- A user choice that does not flip the resolved theme, an OS change under `system`, reduced motion, and a browser without `startViewTransition` change the theme with no circle.
- `theme.preference` remains the only theme key in `localStorage`.

## Definition of Done

- [x] `npm test` covers the reduced-motion skip and the same-theme skip, and passes.
- [x] The acceptance items above hold on the resume page.
- [x] The circle is measured on the running page, not inferred from a build: the radius path is monotonic `0 → 1200px` over ~771ms at ~106ms sampling.
- [x] [brand book](../../brand-book/init.md) §1 describes the sliding glass thumb and the solid fallback. §3 lists the radial reveal and `--dur-theme`, with a hard edge. Square corners, no drop shadow, and the rest of “anything else is still” stay.
- [x] [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md) withdraws the rim and supersedes ADR-0011. No refraction filter ships on the edge, the interior, or the page after the reveal.
