> **ID:** task-04
> **Status:** DONE
> **Specs:** [US-04](../init.md), [ADR-0011](../../../auth-gateway/adrs/11-theme-reveal-rim.md), [brand book §3](../../../brand-book/init.md)

## Overview

The circle’s edge refracts on the band [ADR-0011](../../../auth-gateway/adrs/11-theme-reveal-rim.md) accepts. The look is the brand book.

Superseded: [ADR-0012](../../../auth-gateway/adrs/12-theme-reveal-without-rim.md) withdraws the rim and deletes this effect from the page. The task stands as what was built at the time.

## Goals

- One SVG `feDisplacementMap` on a 36px band. Displacement is at most 12px.
- The new theme inside that band is not filtered.
- The filter is gone when the circle finishes.

## Non-goals

- A filter on the disk interior.
- A filter that stays on the page.
- `feTurbulence` or WebGL.

## Definition of Done

- [x] The band matches the ADR.
- [x] Brand book §3 lists the refractive rim.
