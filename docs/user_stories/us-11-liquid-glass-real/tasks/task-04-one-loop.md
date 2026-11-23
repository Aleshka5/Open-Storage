> **ID:** task-04
> **Status:** DONE
> **Specs:** [US-11](../init.md), [ADR-0006](../../../../adrs/6-one-owner-per-frame.md)

## Overview

The blob is one body: the spring drives position, size and radius together, and the pointer leads it.

## Goals

- One frame loop per open popover: measure, compute, paint; nothing else writes the geometry.
- A capsule that leans toward the pointer, stretches between rows, and settles as a circle when the pointer leaves the rows.
- The loop starts on open or on motion, stops on settle, and is disposed with the popover.
- Focus and keyboard moves glide the blob to the focused row, so the effect is not pointer-only.
- The same geometry under reduced motion, placed without the spring.

## Non-goals

- A physics library.
- A second loop.

## Definition of Done

- [x] The geometry module has a test per rule: circle, capsule, lean, clamp, settle, no NaN on a degenerate box.
- [x] A pointer sweep from the trigger into the panel and across three rows produces motion on every step and no jump.
- [x] After the popover closes, the loop reports stopped and no frame is requested.
