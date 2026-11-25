# ADR-0006 The glass thumb is a rounded square

## Status

Accepted. Supersedes the circle and the fixed width in [ADR-0005](5-glass-thumb-is-a-circle.md). The package and the single thumb stay.

## Decision

The theme thumb is one `Glass`. It is a rounded square: corner radius `12px` (`radius` 12), height `2.25rem`, width the selected segment. It translates with `transform`, and that width animates with the same `--dur` and `--ease`. The three labels sit under the glass, so the rim refracts the letters. The glass is `pointer-events: none`. The optics are `frost: 0`, `dispersion: 0.8`, `bend: 1`, `bendWidth: 0.9`, `depth: 1`, `curvature: 0.15`, `strength: 0.18`, `sheen: 0.45`, `sheenWidth: 4`. The tint is `--paper-raised` at 10% opacity. Segments stay square. Without `backdrop-filter`, the thumb is solid `--ink` and the selected label, `--paper`, paints above it.

## Rejected

A circle smaller than the label. A sharp square (`radius` 0). Three glasses that appear and disappear. Labels as children of `Glass`, which the library keeps sharp. Rounding every other corner on the page.

## Cost

The glass exception is a 12px corner, not a circle. The letters sit in the backdrop, so a browser without `backdrop-filter` lifts them back above the solid thumb. Frost stays off. The bend has to reach past the segment padding, or the glyphs sit in the flat middle and do not move.

## Because

A circle leaves the ends of `System` outside the lens. A sharp square reads as the word’s own plate. The letters have to sit under the glass: the library does not refract its children, and the live page behind the element is what `backdrop-filter` bends.
