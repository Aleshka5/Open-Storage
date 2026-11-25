> **ID:** task-01
> **Status:** DONE
> **Specs:** [US-13](../init.md), [ADR-0003](../../../../adrs/3-one-session-store.md), [US-09](../../us-09-storage-theme/init.md)

## Overview

Record the store before either page changes. [US-09](../../us-09-storage-theme/init.md) D1 kept `theme.preference` in each origin’s `localStorage` and rejected a cookie on `.filenkov.store`. The new argument is that the resume page and storage are one browser session for this choice.

## Goals

- One ADR in `adrs/`. It states the session cookie, the rejected stores, the cost, and the risk.
- The ADR says the cookie is not the auth session.

## Non-goals

- Editing `theme.ts`, `index.html`, or the brand book. Those wait until the ADR exists.

## Definition of Done

- [x] The ADR is accepted and linked from [adrs/init.md](../../../../adrs/init.md).
- [x] It names [ADR-0003](../../../../adrs/3-one-session-store.md) as unchanged.
- [x] It records that a leftover `localStorage` key is not read.
