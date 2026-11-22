# US-03 Resume page follows the brand book

## Story

As a reader of `filenkov.store`, I want the resume page to follow the [brand book](../../brand-book/init.md), so the page has one theme control, one pair of palettes, and the same square chrome on every view.

## Status

REVIEW. No page code in this story until the readings below are accepted.

## Scope

`src/auth-gateway/resume-page` only. It is the only frontend in this repository, and it is the hub. The palette, the theme rules, and the check list stay owned by the [brand book](../../brand-book/init.md). This story does not copy them.

## Readings for review

These are how this story reads the brand book against the page that is in the tree. Reject one here and the story changes before any code.

1. The hub keeps its owl tab icon, as the brand book allows. The header mark stays the diamond already in the header. The wordmark destination is `https://filenkov.store`. On that origin the click is an in-app navigation to `/`.
2. A missing, unreadable, or unknown `theme.preference` paints dark. A first visit after this story is dark. Today the page is light only, `:root` holds the light palette, and `<meta name="color-scheme">` is `light`.
3. Corners are square and a panel has no drop shadow: the chat panel, the greeting bubble, art frames, code blocks, the account switch, and focus rings. Marks stay round: the owl art and its hit target, the spine dots, and the owl progress ring (2px `--accent`).
4. A theme segment is at least `2.25rem` tall with square corners. Its width follows the label. The labels are `light`, `Dark`, and `System`.
5. The page grows no toast. `.banner` and `.banner.error` gain the book’s faces so a later toast can use them.
6. The art lightbox and the owl chat mount on `document.body`. Both are viewport layers inside a view that transforms while it enters.

## Already in place

Leave these alone: self-hosted Fraunces and Public Sans, the two Latin preloads, `font-display: swap`, the grain layer, the diamond header mark, the motion tokens, the reduced-motion durations, the view entrance on the Y axis only (and `animation: none` under reduced motion), the choice-row bar, and the wordmark hiding at 620px.

## Acceptance

- `data-theme` is `light` or `dark` before first paint, and `color-scheme` on the document and the meta tag matches it. `:root` carries the dark palette. `[data-theme="light"]` replaces every color token.
- `theme.preference` is `light`, `dark`, or `system`. Anything else behaves as `dark`. `system` keeps listening to `prefers-color-scheme`. Changing the theme does not reload the page. A storage failure is silent. The page still does not store a session in `localStorage`.
- The header’s right slot holds a radiogroup named `Theme` with those three labels. The selected segment’s fill is `--ink` and its label is `--paper`. An unselected segment is transparent, its label is `--ink`, and its hover fill is `--chip`. Arrow keys move inside the group. At 620px the control stays.
- Buttons, fields, and banners set both faces and use the book’s tokens. `.btn-ghost` border matches its transparent fill. The error banner uses `--danger-wash`. A 2px focus ring uses `--accent-text`. `--accent` is not text.
- The chat field sets `color: var(--ink)`. The chat panel and the greeting bubble have no radius and no shadow.
- `npm test` and `npm run build` pass. The initial JS budget stays 95 KB gzipped.
- [frontend/design.md](../../auth-gateway/frontend/design.md) links this outcome. It does not restate the palette.

## Out of scope

- Frontends on other hosts. They are not in this repository.
- The owl mascot, the chat behavior, the tree, and the registry rules.
- A toast, a second theme store, or a font CDN.
- Editing the brand book.

## Tasks

1. [Theme](tasks/task-01-theme.md)
2. [Square chrome](tasks/task-02-square-chrome.md)
3. [Checks and the design note](tasks/task-03-checks.md)
