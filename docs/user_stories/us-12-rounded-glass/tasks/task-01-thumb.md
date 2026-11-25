> **ID:** task-01
> **Status:** DONE
> **Specs:** [US-12](../init.md), [ADR-0006](../../../../adrs/6-glass-thumb-is-a-rounded-square.md)

## Overview

Replace the circle with one rounded square on both React pages, and put the labels under it.

## Goals

- One `Glass`, radius 12, width taken from the selected segment.
- Labels behind the glass. The resume page still loads the package off the initial chunk.

## Non-goals

- The reveal circle.
- Segment shape.

## Definition of Done

- [x] Both theme controls place one rounded square and set its width from the label.
- [x] The brand test and the SPA theme test match that shape.
