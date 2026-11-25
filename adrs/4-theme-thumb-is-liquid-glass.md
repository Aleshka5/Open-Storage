# ADR-0004 The theme thumb is liquid glass

## Status

Superseded in part by [ADR-0005](5-glass-thumb-is-a-circle.md). The package and the single thumb stay. The square corners and the thin rim do not.

## Decision

The theme control stays one radiogroup of three states: `light`, `Dark`, and `System`. The sliding thumb is one `Glass` from `@samasante/liquid-glass`, in the package’s material mode. Each React page that renders the control depends on that package. CSS sets the thumb’s box, its tint, and its square corners (`radius` 0). The optics passed in are `frost: 6` and `dispersion: 0.4`. Bend, depth, and strength stay the package’s material defaults. The circle reveal and `theme.preference` stay as they are.

## Rejected

The CSS thumb (`backdrop-filter: blur(14px) saturate(1.7)`, a 1px edge, and a 1px hairline). A rounded thumb taken from the library demos. A popover or a second control. Installing the package in a page that is not React.

## Cost

Both React pages take the dependency. The resume page loads it in its own chunk so the 95 KB initial JS budget still holds. The CSS hairline goes away; the rim is the library’s. Bending the live page is Chrome and Edge. Safari and Firefox frost the thumb and light its edge.

## Because

The CSS blur reads as a translucent plate. The library is the glass material for a React page, and the three states stay one thumb.
