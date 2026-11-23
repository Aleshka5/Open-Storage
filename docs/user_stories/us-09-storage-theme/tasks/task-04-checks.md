> **ID:** task-04
> **Status:** DONE
> **Specs:** [US-09](../init.md), [spa](../../../open-storage/spa/init.md)

## Overview

Lock the theme skips with a test, and record the behaviour in the SPA doc once it is true.

## Goals

- Add a test script if `src/open-storage/spa` has none. Cover the unknown `theme.preference` fallback, the reduced-motion skip, and the same-theme skip.
- `npm run build` passes.
- [spa/init.md](../../../open-storage/spa/init.md) links the brand book for theme and chrome. It does not copy the palettes. The `frontend/` paths that doc still names are a separate mismatch; this task does not rewrite that tree.

## Non-goals

- The app’s Python tests.
- Gateway code and deploy.
- Marking the story done for an item that is not true.

## Definition of Done

- [x] The SPA test script passes, including the three cases above.
- [x] `npm run build` passes.
- [x] US-09’s definition of done is checked only for items that hold.
