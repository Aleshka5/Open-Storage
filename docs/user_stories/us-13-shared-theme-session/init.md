> **ID:** US-13
> **Status:** DONE
> **Specs:** [brand book §1](../../brand-book/init.md), [ADR-0007](../../../adrs/7-theme-preference-is-a-session-cookie.md), [ADR-0003](../../../adrs/3-one-session-store.md), [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md), [resume-page design](../../auth-gateway/frontend/design.md), [spa](../../open-storage/spa/init.md)

## Overview

The resume page (`filenkov.store`) and the storage SPA (`storage.filenkov.store`) each render one `Theme` radiogroup. The thumb is the rounded glass in [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md). Each page writes `theme.preference` to its own `localStorage`. The storage-theme story (US-09, removed) D1 rejected a cookie on `.filenkov.store`, so a choice on one host is invisible on the other. The blocking scripts in both `index.html` files and both `theme.ts` modules read that origin-local key before first paint.

This story reopens that rejection. The two hosts are one browser session for the theme choice. The glass, the labels, and the reveal circle stay.

Tasks: [decision](tasks/task-01-decision.md), [store](tasks/task-02-store.md), [checks](tasks/task-03-checks.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | One store, the cookie `theme.preference`. On `filenkov.store` and `*.filenkov.store` its `Domain` is `.filenkov.store`. Elsewhere `Domain` is omitted. `Path=/`, `SameSite=Lax`, `Secure` only on `https`. No `Max-Age`, no `Expires`, not `HttpOnly`, not `Partitioned`. The value is `light`, `dark`, or `system`. | `localStorage` per origin (US-09, removed, D1). `sessionStorage`. A `Max-Age` that outlives the browser. |
| D2 | The cookie is a UI preference. It is not the auth session. [ADR-0003](../../../adrs/3-one-session-store.md) stays: sessions, logout-all, and not-before stay in the identity provider. Logout does not clear this cookie. The gateway and the storage app do not read it. | A realm attribute, a gateway field, or any write into the identity session. |
| D3 | The head script and `readPreference` read the cookie only. A missing, unreadable, or unknown value paints dark. A leftover `localStorage` key is ignored. No migration. | Reading `localStorage` when the cookie is absent. |
| D4 | Both pages keep their own `ThemeControl`. The thumb stays [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md). The circle stays [ADR-0012](../../auth-gateway/adrs/12-theme-reveal-without-rim.md). | A shared UI package. A new thumb. |

## Goals

- One glass `Theme` control on every view of the resume page and of the storage SPA.
- A choice made on either host paints on the other in the same browser session, before first paint, including a switch in either direction.

## Non-goals

- The Keycloak `filenkov` theme, and the image, rag, audio, llm, observer, and meet hosts.
- A shared component package, a new palette, or a change to the glass optics.
- Putting the preference in the identity session, or clearing it on logout.
- Carrying the choice past the end of the browser session.

## User Story

**As** a person moving between the resume page and storage, I want the same liquid-glass theme control and one saved choice, so the selection I make on either page is the one I see on the other for this browser session.

**Acceptance**

- Every resume-page view and every storage view shows one radiogroup named `Theme`, labels `light`, `Dark`, and `System`, with one rounded glass thumb as in [ADR-0006](../../../adrs/6-glass-thumb-is-a-rounded-square.md). Arrow keys move inside it. At 620px the control stays.
- Choosing a segment writes the session cookie and does not write `localStorage`. The resolved theme paints without a reload. The circle still runs only when [brand book §3](../../brand-book/init.md) says it runs.
- In one browser session, a choice on `filenkov.store` is the choice `storage.filenkov.store` reads before first paint, and the reverse. `data-theme` is `light` or `dark`, and `color-scheme` matches it.
- A missing or unknown cookie paints dark. `system` follows `prefers-color-scheme`. A blocked cookie write still paints and stays silent.
- After the browser session ends, the next visit has no cookie and paints dark.
- Logout, `GET /auth/session`, and `GET /api/auth/me` do not read or write `theme.preference`.

## Definition of Done

- [x] An ADR records D1–D3 and supersedes the shared-cookie rejection in the storage-theme story (US-09, removed) D1. The code change follows that ADR.
- [x] `npm test` and `npm run build` pass in `src/auth-gateway/resume-page` and in `src/open-storage/spa`. The resume page’s initial JS stays inside the 95 KB gzip budget.
- [x] [brand book §1](../../brand-book/init.md) names this cookie as the store. [spa/init.md](../../open-storage/spa/init.md) and [resume-page design](../../auth-gateway/frontend/design.md) link it in one sentence each and do not copy the attributes.
