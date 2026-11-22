## Status

Superseded by [ADR-0012](12-theme-reveal-without-rim.md).

## Decision

A theme circle may refract only on a rim band 36px wide. Displacement stays on that band and is at most 12px. The look of the band is [brand book §3](../../brand-book/init.md).

## Rejected

A refraction filter on the disk interior. The new theme inside the rim would be distorted, and the circle would read as a lens instead of a disk of the new palette.

A refraction filter that remains on the page after the reveal. The filter belongs to the circle’s edge and ends with it.

## Cost

The rim shares the circle’s center, radius, and duration. It has to come off when the circle finishes, including when another choice is waiting to run.

## Because

The reveal is one glass disk, not a glass page. The edge bends. The palette inside it does not, and the page after the circle is the plain theme.

## Order of the waits

The `::view-transition-new(root)` and `::view-transition-group(root)` animations hold the pseudo-elements open, so the transition cannot finish until they do. `vt.finished` is therefore awaited *after* the circle’s own animations, never in the same `Promise.all`: waiting on both at once waits on each other, and the only exit left is the watchdog. The watchdog stays as a backstop for a browser that aborts the transition, and it sits at the circle’s duration plus 120ms.

## How the chain recombines

The filter outputs the page everywhere and the glass band at the rim. Three branches:

1. `SourceGraphic` → `feDisplacementMap` (map = the band) → `feComposite in map` keeps the bend inside the band.
2. That band, saturated to 1.7, with the 1px hairline composited `over` it.
3. `SourceGraphic` intersected with the *inverted* band alpha — the dashed page around the rim.

The final primitive composites branch 2 `over` branch 3. A chain that ends on the hairline `over` the glass alone is the defect this ADR rules out: the hairline covers one pixel, so everywhere else the result is transparent and the band reads as a hole.
