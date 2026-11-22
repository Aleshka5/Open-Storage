> **ID:** US-04
> **Status:** TODO
> **Specs:** [brand book §1](../../brand-book/init.md), [brand book §3](../../brand-book/init.md), [resume-page design](../../auth-gateway/frontend/design.md)

## Overview

The resume page already stores `theme.preference`, paints both palettes, and shows a `Theme` radiogroup (`light`, `Dark`, `System`). The selected segment is a solid `--ink` fill. This story replaces that fill with one glass thumb that slides between the three segments, and reveals a new resolved theme as a circle that starts at the control.

## Locked decisions

| # | Decision |
|---|---|
| D1 | Storage, resolution, first paint, labels, square corners, and the header slot stay as [US-03](../us-03-page-brand/init.md) and the brand book left them. This story does not add a second store. |
| D2 | Selection is one thumb. It translates with `transform` over `--dur`. Unselected segments stay transparent, label `--ink`, hover fill `--chip`. |
| D3 | Glass is the thumb only. Fill is `--paper-raised` at 55% opacity. `backdrop-filter: blur(14px) saturate(1.7)`. A 1px translucent edge and a 1px inset top hairline. No drop shadow. No `feDisplacementMap`, no WebGL, no filter on the page. `will-change: transform` only while the thumb moves. Without `backdrop-filter`, the thumb keeps today’s face: fill `--ink`, label `--paper`. |
| D4 | The circle runs only when a user choice resolves to the other theme. Its center is the theme control’s border box. It grows from 0 until it covers the farthest viewport corner. Inside is the new theme. Outside is the old theme. Mechanism is `document.startViewTransition`, with `clip-path: circle()` on `::view-transition-new(root)`. No second copy of the page. |
| D5 | `--dur-theme` is `700ms` with `--ease`. `prefers-reduced-motion: reduce` sets it to `1ms`, skips the view transition, and jumps the thumb. A missing `startViewTransition` applies the theme in the same turn. First paint, a same-theme choice, and an OS change while the preference is `system` do not wipe. A second click waits until the running transition finishes. |

## Goals

- Slide one glass thumb between the three theme segments.
- Reveal a flipped theme through a circle that starts at the control and fills the viewport.
- Keep the effect on the thumb and on one composited clip.

## Non-goals

- The Keycloak `filenkov` login theme.
- Rounding the control or any other corner.
- A refractive liquid layer across the viewport.
- Changing label casing, the preference key, or the palettes.

## User Story

**As** a visitor, I want the active theme to be a glass thumb that slides, and a theme change to spread from that control as liquid glass, so the new palette arrives in one motion.

**Acceptance**

- The control stays one radiogroup named `Theme`, with labels `light`, `Dark`, and `System`. Arrow keys still move inside it. At 620px it stays.
- The glass thumb slides between the segments. It is the only glass surface. A browser without `backdrop-filter` shows the solid `--ink` face.
- A user choice that flips the resolved theme plays one circle from the control. The new theme is the mask. The old theme stays outside the circle until the circle covers the viewport.
- A user choice that does not flip the resolved theme, an OS change under `system`, reduced motion, and a browser without `startViewTransition` change the theme with no circle.
- `theme.preference` remains the only theme key in `localStorage`.

## Definition of Done

- [ ] `npm test` covers the reduced-motion skip and the same-theme skip, and passes.
- [ ] The acceptance items above hold on the resume page.
- [ ] [brand book](../../brand-book/init.md) §1 describes the sliding glass thumb and the solid fallback. §3 lists the radial reveal and `--dur-theme`. Square corners, no drop shadow, and the rest of “anything else is still” stay.
- [ ] An ADR in `docs/auth-gateway/adrs/` rejects a page-sized refraction filter and points at the brand book for the look. It is written before the page code, in the same change.
