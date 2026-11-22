> **ID:** task-03
> **Status:** DONE
> **Specs:** [US-04](../init.md), [brand book §3](../../../brand-book/init.md)

## Overview

A user choice that flips the resolved theme plays one circle from the control. No refraction filter on the disk.

## Goals

- `document.startViewTransition` and `clip-path: circle()` on `::view-transition-new(root)`.
- The new theme is inside. The old theme stays outside until the circle covers the viewport.
- Skip the circle when the choice does not flip the resolved theme, when the OS changes under `system`, under reduced motion, and without `startViewTransition`.

## Non-goals

- The refractive rim.
- A second copy of the page.

## Definition of Done

- [x] `--dur-theme` is `700ms` with `--ease`, and `1ms` under reduced motion.
- [x] Brand book §3 lists the radial reveal and `--dur-theme`.
