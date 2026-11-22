> **ID:** US-03
> **Status:** DONE
> **Specs:** [brand book](../../brand-book/init.md), [resume-page design](../../auth-gateway/frontend/design.md)

## Overview

The resume page is the only frontend in this repository, and it is the hub. It serves the self-hosted fonts, the grain, the diamond header mark, and the motion tokens, and it follows the brand book for theme and square chrome. The palette stays owned by the brand book. Tasks: [theme](tasks/task-01-theme.md), [square chrome](tasks/task-02-square-chrome.md), [checks](tasks/task-03-checks.md).

## Locked decisions

| # | Decision |
|---|---|
| D1 | The hub keeps the owl tab icon. The header mark stays the diamond. The wordmark destination is `https://filenkov.store`. On that origin the click is an in-app navigation to `/`. |
| D2 | A missing, unreadable, or unknown `theme.preference` paints dark. A first visit after this story is dark. |
| D3 | Square corners and no drop shadow on the chat panel, the greeting bubble, art frames, code blocks, the account switch, and focus rings. The owl hit target, the spine dots, and the owl progress ring stay round. |
| D4 | A theme segment is at least `2.25rem` tall, with square corners. Its width follows the label. Labels are `light`, `Dark`, and `System`. |
| D5 | The page grows no toast. `.banner` and `.banner.error` take the brand book’s faces. |
| D6 | The art lightbox and the owl chat mount on `document.body`. |
| D7 | Leave what already matches: the font files and preloads, `font-display: swap`, the grain, the diamond mark, the motion tokens, the reduced-motion durations, the Y-axis view entrance, the choice-row bar, and the wordmark hiding at 620px. |

## Goals

- Resolve `Light`, `Dark`, or `System` before first paint, and change it from the header without a reload.
- Paint both palettes from one `theme.css`, with `:root` dark.
- Make panels, fields, and focus rings square, with both faces set, and no drop shadow.

## Non-goals

- Frontends on other hosts.
- The owl mascot, the chat behavior, the tree, and the registry rules.
- A toast, a second theme store, or a font CDN.
- Editing the brand book.

## User Story

**As** a reader of `filenkov.store`, I want the resume page to follow the brand book, so the page has one theme control, one pair of palettes, and the same square chrome on every view.

**Acceptance**

- `data-theme` is `light` or `dark` before first paint, and `color-scheme` on the document and the meta tag matches it.
- `theme.preference` is `light`, `dark`, or `system`. Anything else behaves as `dark`. `system` keeps listening to `prefers-color-scheme`. A storage failure is silent. The page does not store a session in `localStorage`.
- The header’s right slot holds a radiogroup named `Theme`. The selected segment’s fill is `--ink` and its label is `--paper`. An unselected segment is transparent, its label is `--ink`, and its hover fill is `--chip`. Arrow keys move inside the group. At 620px the control stays.
- Buttons, fields, and banners set both faces. `.btn-ghost` border matches its transparent fill. The error banner uses `--danger-wash`. A 2px focus ring uses `--accent-text`. `--accent` is not text.
- [frontend/design.md](../../auth-gateway/frontend/design.md) links this outcome and does not restate the palette.

## Definition of Done

- [x] `npm test` passes.
- [x] `npm run build` passes inside the 95 KB initial JS budget.
- [x] The acceptance items above hold on the resume page.
- [x] `docs/auth-gateway/frontend/design.md` links the brand book for theme and chrome.
