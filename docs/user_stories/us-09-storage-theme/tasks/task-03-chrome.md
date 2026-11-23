> **ID:** task-03
> **Status:** DONE
> **Specs:** [US-09](../init.md), [brand book §2](../../../brand-book/init.md), [brand book §4](../../../brand-book/init.md)

## Overview

Panels, fields, focus rings, and toasts on the storage SPA are square, set both faces, and have no drop shadow, in both palettes. Grain, the diamond, and the self-hosted fonts already match the brand book and stay.

## Goals

- Remove the `1px` radius on `:focus-visible`. The ring stays 2px `--accent-text`.
- Buttons, fields, selects, textareas, banners, and toasts set `background` and `color` from the active palette. `--accent` is not text.
- Keep the existing toast calls. The toast face stays the brand banner under both themes.
- Confirm dialogs, the lightbox, and the vault unlock stay on `document.body` through `ViewportPortal`.

## Non-goals

- The theme script and `theme.css` ownership. Those are [task-01](task-01-theme.md).
- The thumb and the circle. Those are [task-02](task-02-thumb-circle.md).
- New screens, and removing toasts.

## Definition of Done

- [x] Focus rings are square. A search of `src/open-storage/spa` for `box-shadow` in CSS finds none on panels, fields, or toasts.
- [x] A control that sets only one face is gone.
- [x] Viewport layers still mount on `document.body`.
