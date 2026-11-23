> **ID:** task-03
> **Status:** TODO
> **Specs:** [US-11](../init.md), [ADR-0005](../../../../adrs/5-liquid-glass-is-optical.md)

## Overview

The effect the request asked for: what is behind the blob bends inside it. [ADR-0005](../../../../adrs/5-liquid-glass-is-optical.md) rejects `backdrop-filter: url(#filter)` because Chromium will not refract a backdrop from an SVG reference, so the source of the displaced image has to be sampled explicitly.

## Goals

- A displacement field generated from a height field, applied to a sample of the backdrop under the blob's box.
- The region clamped to the blob's box each frame, with a ceiling on the filter area.
- The strength a token, with a written ceiling, and zero under `prefers-reduced-transparency`.
- The same field drives the rim's lit arc, so the light and the bend agree.
- The frame cost of the field stated as a number in the task, not an adjective.

## Non-goals

- A viewport-sized canvas.
- A WebGL context that outlives the popover.
- A refraction on the panel's whole area; the panel blurs, the blob bends.

## Definition of Done

- [ ] On the running page, a pixel of the header mark seen through the blob differs from the same pixel beside the blob, in both palettes.
- [ ] With the pointer moving over the open popover, frame times are recorded and none exceeds the stated budget on this host.
- [ ] Under `prefers-reduced-transparency` the banner reads no refraction and every face is the solid brand face.
- [ ] The filter is destroyed with the popover: no context and no canvas survive a close.
