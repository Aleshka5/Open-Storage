> **ID:** US-10
> **Status:** IN PROGRESS
> **Specs:** [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md), [brand book §1](../../brand-book/init.md), [US-04](../us-04-liquid-glass-theme/init.md), [US-09](../us-09-storage-theme/init.md), [spa](../../open-storage/spa/init.md)

## Overview

The storage SPA header's `Theme` control is three labeled segments with a sliding thumb ([US-09](../us-09-storage-theme/init.md) D3). This story replaces that face with the control in [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md): a round glass trigger that shows `light` as a sun, `dark` as a moon, and `system` as a half-filled circle; a pointer over it opens a glass popover slider in which one blob follows the pointer with a spring and morphs from a circle to a pill per row. The state, the key, the palettes, and the reveal circle do not change.

Tasks: [glass tokens](tasks/task-01-glass-tokens.md), [trigger and popover](tasks/task-02-trigger-popover.md), [blob](tasks/task-03-blob.md), [checks](tasks/task-04-checks.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | `theme.preference` stays the only theme key, with the same values and the same fallback ([US-09](../us-09-storage-theme/init.md) D1). Both palettes and `theme.css` stay. | A second key for the open state or the last row |
| D2 | The closed control is one round glass blob with one icon that follows the preference. Labels move into the popover rows: `Light`, `Dark`, `System`. | Keeping the three visible words |
| D3 | A pointer over the trigger opens the popover after 120ms; it closes 400ms after the pointer leaves both the trigger and the popover. `Escape` and an outside pointer press close it at once. | Click-to-open only; a native `<select>` |
| D4 | One element is the blob. Closed, it is the trigger. Open, it is the slider well that follows the pointer and stretches toward it. Its resizing is a pointer loop, not a CSS transition. | A per-row `:hover` fill with no blob |
| D5 | The glass edge is always visible: a 1px rim, a brighter top-left arc, and a 1px inset hairline, over a translucent fill and `backdrop-filter`. The mouse corner stays square; the trigger, the blob and the wells are round. | A rimless fill that reads as a solid chip |
| D6 | A choice still runs the circle from [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md) when that circle applies. Reduced motion places the blob without the spring. | A new reveal for this story |
| D7 | The resume page keeps its segmented control. This story edits the storage SPA only, and the brand book records this control as the storage face. | Reworking both pages in one change |

## Goals

- Show the current theme as one icon blob in the header, and change it from a glass popover.
- Keep the glass readable as glass: a visible edge, a blurred layer behind it, a light arc.
- Move the selection as one blob that the pointer leads with a spring, and keep the keyboard path working.

## Non-goals

- The resume page, the Keycloak login theme, and the brand book palettes.
- A new theme store, a new token name for the palette, or a reload.
- A refraction filter (`feTurbulence`, `feDisplacementMap`) on any edge.
- Rounding the popover's or the header's outer corners.

## User Story

**As** a person using storage, I want the header's theme control to show my current theme as one glass icon that opens a glass slider, so the choice is compact and the control reads as a piece of glass I move.

**Acceptance**

- The header's right slot holds one `button` with `aria-haspopup="dialog"`, accessible name `Theme`, and a visible sun, moon, or half-filled circle for `light`, `dark`, or `system`.
- The closed trigger is a round glass blob: a translucent fill, `backdrop-filter`, a 1px rim, a top-left bright arc, and an inset hairline. The rim is visible against both palettes.
- A pointer over the trigger shows a tooltip `Theme` and opens the popover after 120ms. Leaving the trigger and the popover closes it after 400ms. `Escape`, `Tab` out, and an outside pointer press close it at once.
- The open popover lists `Light`, `Dark`, `System` with their icons, marks the active row, and holds one blob that follows the pointer with a spring and stretches toward it. Over a row the well is a pill; away from the rows it is a circle.
- Choosing a row writes `theme.preference`, paints the resolved theme, plays the circle when the circle applies, closes the popover, and the trigger shows that row's icon.
- `Enter`, `Space`, the arrow keys, and `Home`/`End` work without a pointer, and the blob follows focus.
- `prefers-reduced-motion: reduce` places the blob immediately and opens the popover without the morph.
- Without `backdrop-filter` every glass face falls back to the solid face, and the control still works.
- At 620px the control stays in the header and does not overflow.

## Definition of Done

- [ ] A test locks the open/close state machine (intent delay, grace, `Escape`, outside press), the icon per preference, and the reduced-motion path, and `npm test` passes.
- [ ] The spring and the blob geometry live in a pure module with a test: the blob center converges toward the target, stays inside the panel, and reports a circle radius away from the rows and a pill radius over one.
- [ ] `npm run build` in `src/open-storage/spa` passes.
- [ ] The acceptance items are checked on the running SPA: the popover opens and closes on the pointer, the blob trails the pointer, and the rim is visible in both palettes.
- [ ] [brand book §1](../../brand-book/init.md) and [spa/init.md](../../open-storage/spa/init.md) describe this control, and [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md) is the decision they link.
