> **ID:** US-09
> **Status:** DONE
> **Specs:** [brand book](../../brand-book/init.md), [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md), [US-03](../us-03-page-brand/init.md), [US-04](../us-04-liquid-glass-theme/init.md), [spa](../../open-storage/spa/init.md)

## Overview

`storage.filenkov.store` paints the light palette only. `index.html` sets `color-scheme` to `light`, `:root` in `filenkov.css` holds the light hexes, and the header has no `Theme` control. Grain, the self-hosted fonts, the diamond mark, square toasts, and the 620px wordmark rule are already on the page. This story gives the SPA the same theme and chrome the resume page already ships: both palettes, the glass thumb, and the hard-edged circle. Screens, routes, and the storage API stay.

The directory that edits realm `admin` and `svc:<service>:*` stays on the resume page. It is [frontend design](../../auth-gateway/frontend/design.md).

Tasks: [theme](tasks/task-01-theme.md), [thumb and circle](tasks/task-02-thumb-circle.md), [chrome](tasks/task-03-chrome.md), [checks](tasks/task-04-checks.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The SPA follows [brand book §1](../../brand-book/init.md) and [§3](../../brand-book/init.md). `theme.preference` is the only theme key, stored on this origin. A missing, unreadable, or unknown value paints dark. | A cookie on `.filenkov.store` that copies the resume page’s choice. The two origins do not share `localStorage`. |
| D2 | `:root` is the dark palette. `[data-theme="light"]` replaces every color token. Both blocks live in one `theme.css`. `filenkov.css` stops owning palette hexes. | Leaving today’s light-only `:root` and adding dark as an override |
| D3 | Selection is the glass thumb in brand book §1. A flipped theme is the circle in brand book §3, with the hard edge fixed by [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md). Superseded for the control’s face by [US-10](../us-10-liquid-glass-theme-control/init.md) / [ADR-0004](../../../adrs/4-liquid-glass-theme-control.md); state, key and circle unchanged. | A solid selected segment, or a refractive rim on the circle |
| D4 | Routes, screens, and `/api/**` stay. Identity stays `GET /api/auth/me`. | Pointing the SPA at gateway `GET /auth/session` |
| D5 | Toasts stay. Their face is the brand banner: square, no shadow, both faces set. | Removing toasts to match the resume page, which grows none |
| D6 | The tab icon stays the diamond in the brand book. The owl stays on the hub. | The owl as the storage favicon |
| D7 | This story does not edit the brand book, the resume page, or [spa/init.md](../../open-storage/spa/init.md) until the behaviour is true. The doc then links the brand book. It does not copy the palettes. | Restating token tables in the SPA doc |

## Goals

- Resolve `light`, `Dark`, or `System` before first paint, and change it from the header without a reload.
- Paint both palettes from one `theme.css`.
- Slide one glass thumb, and reveal a flipped theme as one circle from that control.

## Non-goals

- The resume page, the Keycloak `filenkov` theme, and the brand book text.
- A stack change. React 18, Vite 6, and react-router 6 stay.
- The file manager, photo grid, vault, resumes, and admin quota page, beyond the chrome this story names.
- A second theme store, a font CDN, or a shared preference across hosts.

## User Story

**As** a person using storage, I want the same theme control and chrome as the resume page, so light, Dark, and System look and move the same way on both hosts.

**Acceptance**

- `data-theme` is `light` or `dark` before first paint, and `color-scheme` on the document and the meta tag matches it. An unknown `theme.preference` behaves as `dark`. `system` follows `prefers-color-scheme`.
- The header’s right slot has one radiogroup named `Theme`, labels `light`, `Dark`, and `System`. Arrow keys move inside it. At 620px the wordmark hides and the control stays.
- The glass thumb is the only glass on the page. A browser without `backdrop-filter` shows the solid `--ink` face.
- A user choice that flips the resolved theme plays one circle from the control. The edge is a hard cut. No SVG filter remains after it. A same-theme choice, an OS change under `system`, reduced motion, and a missing `startViewTransition` change the theme with no circle.
- Buttons, fields, banners, and toasts set both faces from the active palette. `--accent` is not text. Focus rings are square. Panels have no drop shadow.
- `GET /api/auth/me` is still the session probe. No route path changes.

## Definition of Done

- [x] A test locks the unknown-key fallback, the reduced-motion skip, and the same-theme skip, and the SPA test script passes.
- [x] `npm run build` in `src/open-storage/spa` passes.
- [x] The acceptance items above hold on the storage SPA.
- [x] [spa/init.md](../../open-storage/spa/init.md) links the brand book for theme and chrome and does not copy the palettes.
