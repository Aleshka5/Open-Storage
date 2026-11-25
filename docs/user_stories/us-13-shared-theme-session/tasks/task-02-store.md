> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-13](../init.md), [brand book §1](../../../brand-book/init.md)

## Overview

Both pages read and write the session cookie from [task-01](task-01-decision.md). The glass control stays.

## Goals

- The blocking script in `src/auth-gateway/resume-page/index.html` and in `src/open-storage/spa/index.html` reads the cookie before first paint.
- `readPreference` and `persist` in both `theme.ts` modules use that cookie and do not call `localStorage`.
- On `filenkov.store` and `*.filenkov.store`, the cookie’s `Domain` is `.filenkov.store`. On any other host, `Domain` is omitted.
- [brand book §1](../../../brand-book/init.md) owns the attributes. Each page doc links it in one sentence.

## Non-goals

- The thumb, the circle, and a shared component package.
- The gateway, the storage API, and the identity session.

## Definition of Done

- [ ] A choice writes `theme.preference` as a session cookie and does not write `localStorage`.
- [ ] An unknown cookie value paints dark.
- [ ] The brand book, [spa/init.md](../../../open-storage/spa/init.md), and [resume-page design](../../../auth-gateway/frontend/design.md) match the store.
