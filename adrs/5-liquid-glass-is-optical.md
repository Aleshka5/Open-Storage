# ADR-0005 Liquid glass is an optical effect, and it is the one glass in the header

## Status

Accepted. It refines [ADR-0004](4-liquid-glass-theme-control.md): the shape and the motion that ADR fixes stay, and this ADR fixes what makes the glass read as glass.

## Decision

The glass on the theme control is one refracting surface, and every part of it is generated from one shader, not assembled from CSS layers.

1. **A refracting layer.** The surface renders what is behind it, displaced: a `feDisplacementMap` fed by an `feTurbulence`-generated height field, so the header's mark, its wordmark and the page under the popover bend inside the blob the way a thick lens bends them. A blur is not enough: a flat blurred fill reads as frosted plastic.
2. **One continuous light source.** The rim is lit, not stroked. Every glass face derives its highlight from one light direction (top-left) and its rim is brighter where the surface turns away from that light. A 1px uniform border does not read as an edge of a solid body.
3. **One material for trigger, bubble, blob and panel.** They share the same tokens (fill, blur, rim, arc, dispersion), the same filter chain and the same corner geometry, so the morph from the trigger into the blob is a change of shape in one material, not a swap between elements.
4. **Dispersion at the edge.** The rim splits the light: a faint warm fringe on the lit arc and a faint cool fringe opposite it. The brand's copper `--accent` biases the warm side, so the effect belongs to the palette instead of being a generic blue chrome.
5. **The blob moves as one body.** One spring drives position, size and radius together; the shape it takes over a row is a capsule whose ends stay rounded, and the transition between rows is a stretch, not a cross-fade. The pointer leads; nothing snaps, and no loop runs while the popover is closed.
6. **The composition reports frames, not guesses.** The spring, the refraction source and the light direction are computed once per frame from the trigger's box, in one loop. A second loop, or a CSS animation racing the loop, is a defect.

## Rejected

- **A CSS-only glass** of translucent fill, `backdrop-filter` and a 1px border. That is what ships today ([US-10](../docs/user_stories/us-10-liquid-glass-theme-control/init.md)); it reads as frosted plastic, and the request was a liquid glass.
- **`backdrop-filter: url(#svg-filter)`.** Chromium does not accept an SVG reference in `backdrop-filter`, so it cannot refract what is behind the element; the filter would see the element, not its background.
- **A per-frame canvas copy of the backdrop** on a full-screen layer. It is the cost [ADR-0012](../docs/auth-gateway/adrs/12-theme-reveal-without-rim.md) refused once; scoping it to a 40px blob is acceptable, a viewport canvas is not.
- **Rounding the popover panel.** Corners stay square by the brand book; only the trigger, the blob and the wells inside the rows are round.
- **A glass decoration on any other element.** The brand book keeps this control as the one glass in the header; a second one dilutes it.

## Cost

A filter chain on four small elements, a WebGL or canvas path for the refraction, and one frame loop that only runs while the popover is open or the blob is moving. The control becomes the most expensive thing in the header, so its GPU budget is bounded and measured rather than assumed.

## Risk

A refraction filter is invisible under `prefers-reduced-transparency` and must be, or the surface becomes unreadable. `feDisplacementMap` cost scales with the filter area, so a mis-sized region drops frames on a laptop; the region is clamped to the blob's box, never the viewport. A refraction that is too strong hides the labels behind it; the strength is a token with a ceiling, and the text contrast check in the brand book still holds over the glass.
