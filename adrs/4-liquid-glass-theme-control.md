# ADR-0004 Liquid glass theme control with icons and a cursor-following blob

## Status

Proposed. It reopens the thumb of [ADR-0012](../docs/auth-gateway/adrs/12-theme-reveal-without-rim.md), which stays in force for the theme circle.

## Decision

The header's `Theme` control stops being three labeled segments. It is a round glass trigger, and the palette is a popover under it.

1. The trigger shows the current preference as one icon: a sun for `light`, a moon for `dark`, a half-filled circle for `system`. The accessible name is `Theme`, the current choice is in `aria-label` and in `aria-haspopup="dialog"`.
2. The closed control is one glass blob. The glass keeps the ADR-0012 palette and reads as glass, not as a filled chip: a translucent `--paper-raised` fill at up to 55% opacity, `backdrop-filter: blur(16px) saturate(1.6)`, a 1px `--glass-rim` edge with a brighter top-left arc, and a 1px inset white hairline. The edge is visible at rest, on hover, and while the blob moves, so the transparency reads as a surface with a boundary.
3. A pointer over the trigger opens the popover after a 120ms intent delay. It stays open while the pointer is over the trigger or the popover and closes 400ms after it leaves both. `Escape` and a pointer press outside close it at once. The popover traps no focus; it closes and returns focus to the trigger on `Escape`.
4. Opening morphs the trigger blob into a vertical liquid-glass slider panel that grows out of the trigger. The slider is the popover: three rows, each a lens well, at 56px. The blob is one element that follows the pointer with a soft spring (stiffness 0.18, damping 0.78, capped at 34px per frame). Over a row it stretches toward the pointer and the well it covers morphs from a circle to a pill. It does not snap.
5. Choosing a row writes `theme.preference`, paints the resolved theme, and plays the circle from ADR-0012 when that circle applies. The row's icon is the icon the trigger then shows.
6. Keyboard: `Tab` reaches the trigger, `Enter` or `Space` opens and focuses the selected row, arrow keys move, `Enter` or `Space` chooses, `Escape` closes. Focus makes the blob glide to the focused row, so the control is not pointer-only.
7. Reduced motion turns the spring into an immediate placement and does not change the control's shape rules. Without `backdrop-filter`, the blob and the panel take the solid face the brand book already fixed.

## Rejected

- Labeled segments with a sliding thumb. They carry three words in the header for one preference, and the request is a compact icon.
- A native `<select>`. The system popup cannot hold a blob, glass, or the morph.
- A click-to-open menu. The request opens on the pointer reaching the icon.
- A continuously tracking blob with no spring. The blob would jump between rows and lose the liquid read.
- Rounded popover corners. Corners stay square; only the interior wells and the blob are round.
- `feTurbulence`/`feDisplacementMap` on the blob edge. ADR-0012 withdrew the refractive rim: it does not read at this size and costs a per-frame canvas.

## Cost

The control gains a pointer state machine, a pointer-move animation loop, and a popover that must not fight the header's scroll-hide script. The header no longer shows three labeled options, so a first-time visitor learns the icons from the popover labels.

## Risk

A dropdown that opens on hover can flicker or capture a pointer that only passes the header on its way somewhere else: the 120ms intent delay and the 400ms grace bound it. A blob that follows the pointer is decoration over a choice; a screen reader and the keyboard path never depend on it, and every row keeps its text label.
