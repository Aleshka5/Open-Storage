> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-09](../init.md), [brand book §1](../../../brand-book/init.md), [brand book §3](../../../brand-book/init.md), [ADR-0012](../../../auth-gateway/adrs/12-theme-reveal-without-rim.md)

## Overview

The `Theme` control selects with one glass thumb. A user choice that flips the resolved theme plays one circle from that control. The behaviour is the one the resume page already ships in `src/auth-gateway/resume-page/src/components/ThemeControl.tsx` and `src/auth-gateway/resume-page/src/themeReveal.ts`. This task does not restate it.

## Goals

- One thumb translates with `transform` over `--dur`. Glass is `backdrop-filter`. Without it, the thumb is the solid `--ink` face. It is the only glass this task leaves on the page.
- `document.startViewTransition` and `clip-path: circle()` on `::view-transition-new(root)`. The new theme is inside. The old theme stays outside until the circle covers the viewport. The edge is a hard cut.
- Skip the circle when the choice does not flip the resolved theme, when the OS changes under `system`, under reduced motion, and without `startViewTransition`.

## Non-goals

- A refractive rim. [ADR-0012](../../../auth-gateway/adrs/12-theme-reveal-without-rim.md) withdrew it.
- A second copy of the page, or a second `localStorage` key.
- Editing the resume page’s reveal.

## Definition of Done

- [ ] The thumb slides, and the solid `--ink` face is the fallback.
- [ ] `--dur-theme` is `700ms` with `--ease`, and `1ms` under reduced motion.
- [ ] No SVG filter is drawn at the circle’s edge, and none remains after the reveal.
