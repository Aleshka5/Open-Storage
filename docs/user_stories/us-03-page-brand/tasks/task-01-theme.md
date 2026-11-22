> **ID:** task-01
> **Status:** TODO
> **Specs:** [US-03](../init.md), [brand book](../../../brand-book/init.md)

## Overview

The resume page resolves `light`, `Dark`, and `System` before first paint, and the header changes that choice without a reload. Files: `index.html`, `src/styles/theme.css`, `src/styles/tokens.css`, `src/components/Layout.tsx` under `src/auth-gateway/resume-page`.

## Goals

- Run the brand book’s `readPreference`, `resolve`, and `apply` from a blocking script in `<head>`.
- Put both palettes, the button faces, the banner faces, and the motion tokens in `theme.css`. `:root` is the dark palette.
- Put the `Theme` radiogroup in the header’s right slot, beside the session control.
- Point the wordmark at `https://filenkov.store`, as an in-app navigation to `/` on that origin.

## Non-goals

- Square corners, drop shadows, and viewport layers. Those are [task-02](task-02-square-chrome.md).
- Tests and the design note. Those are [task-03](task-03-checks.md).
- A toast.

## Definition of Done

- [ ] `data-theme` and `color-scheme` are set before first paint.
- [ ] `theme.preference` stores the preference. An unknown value behaves as `dark`. `system` follows `prefers-color-scheme`.
- [ ] `[data-theme="light"]` replaces every color token. `--surface-raised` and `--danger-wash` exist. The error banner uses `--danger-wash`.
- [ ] The radiogroup name is `Theme`, and its labels are `light`, `Dark`, and `System`.
