> **ID:** task-01
> **Status:** TODO
> **Specs:** [US-09](../init.md), [brand book §1](../../../brand-book/init.md), [brand book §2](../../../brand-book/init.md)

## Overview

The storage SPA resolves `light`, `Dark`, and `System` before first paint, and the header changes that choice without a reload. Files under `src/open-storage/spa`: `index.html`, `src/styles/theme.css`, `src/styles/filenkov.css`, `src/components/Layout/Header.tsx`.

## Goals

- Run the brand book’s blocking script in `<head>`. `data-theme` and `color-scheme` are set before first paint.
- Put both palettes, the button faces, the banner faces, and the motion tokens in `theme.css`. `:root` is dark. `[data-theme="light"]` replaces every color token, including `--surface-raised`.
- Remove the palette hexes from `filenkov.css`. Layout, type, and the grain stay there.
- Put the `Theme` radiogroup in the header’s right slot. The wordmark still links to the hub.

## Non-goals

- The glass thumb and the circle. Those are [task-02](task-02-thumb-circle.md).
- Square focus rings and toast faces. Those are [task-03](task-03-chrome.md).
- Tests. Those are [task-04](task-04-checks.md).

## Definition of Done

- [ ] `data-theme` and `color-scheme` are set before first paint.
- [ ] `theme.preference` stores the preference on this origin. An unknown value behaves as `dark`. `system` follows `prefers-color-scheme`.
- [ ] `filenkov.css` no longer contains a palette hex.
- [ ] The radiogroup name is `Theme`, and its labels are `light`, `Dark`, and `System`.
