> **ID:** task-01
> **Status:** DONE
> **Specs:** [US-10](../init.md), [ADR-0004](../../../../adrs/4-liquid-glass-theme-control.md), [brand book §2](../../../brand-book/init.md)

## Overview

The bright arc and the rim need a token that works on both palettes. `theme.css` owns the palettes; this task adds the glass tokens to the same file and nothing else.

## Goals

- `--glass-fill`: the translucent fill the blob and the panel use.
- `--glass-rim`: the 1px edge, visible on both palettes.
- `--glass-arc`: the brighter top-left arc.
- `--glass-sheen`: the inset hairline.
- `--glass-blur`: the `backdrop-filter` value, one place for the trigger, the panel and the blob.

## Non-goals

- A new palette, or a change to any existing token value.
- A glass face for any element other than this control.

## Definition of Done

- [x] The five tokens are in `src/styles/theme.css` for both palettes, and the reduced-motion block is untouched.
- [x] No other stylesheet gains a glass face.
