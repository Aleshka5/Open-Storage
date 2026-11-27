# ADR-0007 Theme preference is a session cookie

## Status

Accepted. Supersedes the shared-cookie rejection in the storage-theme story (US-09, removed) D1. [ADR-0003](3-one-session-store.md) is unchanged.

## Decision

`theme.preference` is one session cookie, not per-origin `localStorage`. This supersedes the shared-cookie rejection in the storage-theme story (US-09, removed) D1. [ADR-0003](3-one-session-store.md) is unchanged: the cookie is a UI preference, not the auth session. Logout does not clear it. The gateway and the storage app do not read it.

[Brand book §1](../docs/brand-book/init.md) owns the cookie attributes. Read the cookie only. Ignore a leftover `localStorage` key. No migration. Persist the choice, never the resolved theme. A blocked write is silent and the page still paints.

## Rejected

`localStorage` per origin. `sessionStorage`. A `Max-Age` that outlives the browser. A realm attribute or any write into the identity session.

## Cost

The choice dies when the browser session ends. The first visit after cutover paints dark.

## Risk

The cookie is sent on requests to `*.filenkov.store` and those servers ignore it. A browser that blocks cookies does not remember the choice.

## Because

The resume page and the storage SPA are one browser session for this choice. A choice on one host has to paint on the other before first paint.
