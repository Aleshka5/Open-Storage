> **ID:** task-03
> **Status:** TODO
> **Specs:** [US-13](../init.md)

## Overview

Lock the cookie contract in the tests that already cover `theme.preference`.

## Goals

- Each page’s tests cover a missing cookie, an unknown value, a `system` value, a silent write failure, and the absence of a `localStorage` write.
- A test sets the cookie the way `filenkov.store` would and reads it back as `storage.filenkov.store` would: same name, `Domain=.filenkov.store`, no `Max-Age`.

## Non-goals

- A browser suite across two live hosts.
- The glass optics and the reveal circle. Their tests stay.

## Definition of Done

- [ ] `npm test` passes in both React pages.
- [ ] `npm run build` passes in both. The resume page’s initial JS stays inside 95 KB gzipped.
