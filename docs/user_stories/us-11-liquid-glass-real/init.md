> **ID:** US-11
> **Status:** TODO
> **Specs:** [ADR-0005](../../../adrs/5-liquid-glass-is-optical.md), [ADR-0006](../../../adrs/6-one-owner-per-frame.md), [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md), [brand book §1](../../brand-book/init.md), [US-10](../us-10-liquid-glass-theme-control/init.md), [spa](../../open-storage/spa/init.md)

## Overview

[US-10](../us-10-liquid-glass-theme-control/init.md) gave the theme control its shape: an icon trigger, a hover popover, one blob. The shape is not the effect. The blob is a translucent fill with `backdrop-filter` and a 1px border, so it reads as frosted plastic; it mounts, but it does not travel with the pointer, because a CSS transition and a frame loop both write its position.

This story makes the glass read as glass and makes the blob one moving body. [ADR-0005](../../../adrs/5-liquid-glass-is-optical.md) fixes what the material is; [ADR-0006](../../../adrs/6-one-owner-per-frame.md) fixes who writes the geometry. The state, the key, the palettes, the reveal circle and the accessibility tree do not change.

Tasks: [the defect](tasks/task-01-the-defect.md), [material](tasks/task-02-material.md), [refraction](tasks/task-03-refraction.md), [the one loop](tasks/task-04-one-loop.md), [checks](tasks/task-05-checks.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The glass is a refracting surface: a displacement field bends what is behind the blob, and the light in the rim comes from one direction. Strength, dispersion and rim light are tokens with a ceiling. | A blurred translucent fill with a uniform border, which is today's face |
| D2 | The blob's geometry has one writer: the frame loop. No CSS transition and no React state write `left`, `top`, `width`, `height` or `border-radius`. | A transition that animates the same properties as the loop |
| D3 | The blob and the panel live in one fixed layer on the body. The header's stacking context and `overflow` do not place them. | An absolutely positioned child inside `.header` |
| D4 | The pointer is one `pointermove` listener on the document, re-bound every render; the row under it comes from the coordinate against the row boxes. | One enter event per row; a stale closure from the render that opened |
| D5 | Trigger, bubble, blob and panel are the same material: one fill, one blur, one filter chain, one light. The morph changes the shape, not the substance. | Different glass recipes for the trigger and the panel |
| D6 | `prefers-reduced-transparency` and `prefers-reduced-motion` are honoured: no refraction and no spring, and the face becomes the solid brand face. Text stays legible over the glass on both palettes. | A decorative effect that survives a request for less |
| D7 | The panel keeps square corners and the header keeps no drop shadow. Only the trigger, the blob and the wells inside the rows are round. | Rounding the popover to match the blob |
| D8 | The frame loop costs are bounded and measured: it runs only while open or moving, stops on settle, and requests no frame while the control is closed. | A permanent `requestAnimationFrame` for a 40px decoration |

## Goals

- A glass that refracts: the header's mark and the page content visibly bend inside the blob.
- A rim that reads as the edge of a solid body: lit on the light side, with a faint dispersion fringe.
- One blob that follows the pointer with a spring, stretches between rows, and morphs circle ↔ capsule without a jump.
- The same material on every glass face of this control, in both palettes.
- Proof from the running page: frame times, no frame while closed, and a pixel check that the background is displaced.

## Non-goals

- The resume page, the Keycloak login theme, and the brand book palettes.
- Any second glass element in the header.
- A viewport-sized effect. The refraction is clamped to the blob's box.
- A new theme store, a new key, or a reload.
- Changing the accessible tree: same button, same dialog, same three radios, same labels.

## User Story

**As** a person changing my theme, I want the control to be a piece of real glass — one that bends what is behind it and moves as a single drop — so the theme choice feels like handling a material instead of toggling a checkbox.

**Acceptance**

- The closed trigger is a round glass blob. At rest its rim is visible on both palettes, and the surface shows the header's mark and the page behind it displaced, not just blurred.
- A pointer over the trigger keeps the blob as one body: it widens into a capsule, and its bottom edge holds a sag; the light in its rim stays on the same side through the whole morph.
- The popover opens after the intent delay. The blob then follows the pointer with one spring: it trails, it stretches toward the pointer, over a row it is a capsule, off the rows it is a circle, and it never jumps between rows.
- Moving the pointer from the trigger across the gap into the panel does not close the popover: the panel overlaps the trigger's edge and the moves are reported on the control.
- Choosing a row writes `theme.preference`, paints the resolved theme, plays the reveal circle when it applies, closes the popover, and the trigger shows that row's icon.
- The keyboard path works with no pointer: `Enter`/`Space` opens, arrows and `Home`/`End` move, the blob glides to the focused row, `Enter`/`Space` chooses, `Escape` closes and returns focus.
- With `prefers-reduced-motion`, the blob is placed without a spring. With `prefers-reduced-transparency`, the refraction is off and every glass face is the solid brand face.
- While the control is closed, the page requests no animation frame for it.
- At 620px the control stays in the header and the panel does not overflow the viewport.

## Definition of Done

- [ ] The blob's five geometry values are written by the loop only; the stylesheet contains no transition or keyframe for them, and a test asserts it.
- [ ] The frame loop is started on open or on pointer motion, stops on settle, and the closed state requests no frame: measured on the running page, not inferred.
- [ ] A pure geometry module with a test per rule: the circle under the pointer, the capsule over a row, the lean, the clamp, the settle.
- [ ] The refraction is measured on the running page: a pixel of the header mark inside the blob differs from the same pixel beside it, and the region is the blob's box, not the viewport.
- [ ] Frame times while the pointer moves over the open popover are recorded: no frame over budget on this host, and the budget is stated.
- [ ] Text over the glass passes the brand book's contrast rule on both palettes, measured on the rendered page.
- [ ] `npm test` and `npm run build` pass in `src/open-storage/spa`, and every existing test is green, including `themeBlob.test.ts` re-pointed at the current geometry.
- [ ] The brand book and [spa/init.md](../../open-storage/spa/init.md) describe the material in one short paragraph each and link [ADR-0005](../../../adrs/5-liquid-glass-is-optical.md); no token table is copied.
- [ ] US-10 is marked DONE or SUPERSEDED for the parts this story replaces, so the two do not both claim the control.
- [ ] The scratch files of the US-10 investigation (`themeHarness.*`, any probe) are removed from `src/` or moved out of the build.
