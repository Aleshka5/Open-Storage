> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-11](../init.md), [ADR-0005](../../../../adrs/5-liquid-glass-is-optical.md), [brand book §1](../../../brand-book/init.md)

## Overview

One material for the trigger, the bubble, the blob and the panel. Today each face carries its own fill, border and blur, so the morph swaps substances instead of changing one shape.

## Goals

- One token set: fill, blur, rim, arc, dispersion, strength ceiling. One place that owns them.
- A lit rim from one light direction: brighter on the top-left arc, dimmer opposite, with the sheen inside.
- A faint dispersion fringe, warm side biased by `--accent`.
- The same recipe on the panel, so the blob over a row and the row itself do not disagree.

## Non-goals

- The refraction, which is [task-03](task-03-refraction.md).
- A glass face on anything outside this control.

## Definition of Done

- [ ] Every glass face of the control resolves to the same `--glass-*` set, and no face hard-codes a colour.
- [ ] The rim is visible against both palettes on the rendered page.
- [ ] Text over the glass meets the brand book contrast rule in both palettes, measured.
