## Status

Accepted. Supersedes [ADR-0011](11-theme-reveal-rim.md).

## Decision

The theme reveal is one circle. There is no refractive rim, no displacement filter, no specular hairline, and no SVG filter of any kind on the circle’s edge. The circle’s boundary is a hard cut from the old theme to the new one.

The reveal keeps its shape: `document.startViewTransition` with `clip-path: circle()` on `::view-transition-new(root)` over `--dur-theme` with `--ease`, from the control’s border box to the farthest viewport corner. The sliding glass thumb on the control is unaffected and stays.

## Rejected

[ADR-0011](11-theme-reveal-rim.md) accepted a 36px band, radial through one SVG `feDisplacementMap`, at most 12px, saturated to 1.7, with a 1px specular hairline.

It is withdrawn because the effect cannot be seen. On the resume page at its real size the band is a 36px arc under a circle that crosses the viewport in 700ms, so the bend is present for a fraction of a second at the edge of the screen and reads as nothing. Two implementation defects were fixed before the decision (the chain ended on a flood that covered one pixel, and the page was never recombined), and the effect worked afterwards: measured on the running page, the band displaced content, held a hairline, and left the disk interior byte-identical. It still did not read as glass to the person using it.

The cost was not only the look. The rim owned a per-frame canvas that re-encoded a viewport-sized PNG roughly every 40ms for the length of the reveal, an SVG filter graph of eleven primitives, `getContext('2d')` failing silently in any environment without a 2D context, and a set of tests that asserted the graph’s shape rather than its appearance. A filter that a reader cannot see does not pay for that.

Also rejected: keeping the rim behind a flag. A switched-off effect is still an effect to maintain, and the repo has no second consumer for it.

## Cost

The reveal is plainer: one hard-edged circle instead of a glass disk. Nothing else in the page’s look changes.

## Because

An effect either reads or it does not, and the observer is the only judge. The rim was measured, correct, and invisible. The circle alone carries the reveal, so the code that produced the rim is deleted rather than disabled.
