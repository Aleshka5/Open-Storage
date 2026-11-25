> **ID:** task-01
> **Status:** DONE
> **Specs:** [US-10](../init.md), [ADR-0004](../../../../adrs/4-theme-thumb-is-liquid-glass.md)

## Overview

Replace the CSS thumb with `Glass` on the storage SPA and the resume page. The radiogroup, the labels, and the slide stay.

## Goals

- Depend on `@samasante/liquid-glass` in both React pages.
- The thumb is one `Glass`. CSS owns the box, the tint, and the square corners.

## Non-goals

- The circle reveal.
- The Keycloak theme.

## Definition of Done

- [x] Both `ThemeControl` components render `Glass` as the thumb.
- [x] The CSS thumb no longer sets `backdrop-filter`, a border, or a hairline.
