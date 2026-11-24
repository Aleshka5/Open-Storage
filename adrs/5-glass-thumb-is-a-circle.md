# ADR-0005 The glass thumb is a circle

## Status

Accepted. Supersedes the shape and the rim in [ADR-0004](4-theme-thumb-is-liquid-glass.md). The package and the single thumb stay.

## Decision

A glass element is a circle. Every other corner on the page stays square. The theme thumb is one `Glass`, `2.25rem` square, `radius` 999, centered on the selected label. It translates with `transform`. Its width does not follow the label. The tint is `--paper-raised` at 18% opacity. The optics are `frost: 8`, `dispersion: 0.7`, `bend: 0.85`, `bendWidth: 0.28`, `depth: 0.45`, `strength: 0.16`, `sheen: 0.9`, `sheenWidth: 8`.

## Rejected

A square plate the size of the label. Three separate glasses that appear and disappear. Rounding every corner on the page.

## Cost

The square-corner rule has one exception, and it is only the glass. The thicker rim is the library’s sheen, so the edge is visible on a flat header.

## Because

A square the width of the word reads as that word’s own background. A 1px rim on that square does not read as glass. One circle sliding between the three labels is one object.
