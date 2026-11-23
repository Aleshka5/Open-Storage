> **ID:** task-03
> **Status:** DONE
> **Specs:** [US-10](../init.md), [ADR-0004](../../../../adrs/4-liquid-glass-theme-control.md)

## Overview

One element and one pointer loop. The loop writes the blob's centre, its radius and its insets; CSS owns the glass, the rim and the arc.

## Goals

- A spring: stiffness 0.18, damping 0.78, ≤34px per frame, and a stop when the blob is within 0.5px of the target and its velocity is under 0.5.
- Away from the rows the blob is a circle of 14px; over a row it is a pill the height of the row minus 8px and half the distance to the pointer.
- The blob is clamped inside the panel with the inset radius.
- Focus and keyboard moves glide the blob to the focused row.
- `requestAnimationFrame` stops when the popover closes; no loop runs while the popover is closed.

## Non-goals

- A physics library.
- The glass paint, which is [task-01](task-01-glass-tokens.md) and [task-02](task-02-trigger-popover.md).

## Definition of Done

- [x] The spring and the geometry are pure functions in their own module with a test.
- [x] The closed state runs no animation frame: the trigger's blob is placed by CSS at rest.
