> **ID:** task-03
> **Status:** TODO
> **Specs:** [US-03](../init.md), [brand book](../../../brand-book/init.md), [resume-page design](../../../auth-gateway/frontend/design.md)

## Overview

The brand-book checks this page can lock are locked by tests. The design note points at the brand book and does not copy the palette.

## Goals

- Test the preference fallback, `system` following `prefers-color-scheme`, both faces on the button and banner classes, `--accent` unused as a text color, and the theme control’s name and three labels.
- State in the design note that this page is the hub, and that theme and chrome follow the brand book.

## Non-goals

- A visual restatement of the palette in `design.md`.
- New product behavior beyond [task-01](task-01-theme.md) and [task-02](task-02-square-chrome.md).

## Definition of Done

- [ ] The tests above pass under `npm test`.
- [ ] `npm run build` passes inside the 95 KB initial JS budget.
- [ ] `docs/auth-gateway/frontend/design.md` names the hub exception and links the brand book for theme and chrome.

```
When done and reviewed:
- [ ] The tests above pass under npm test.
- [ ] npm run build passes inside the 95 KB initial JS budget.
- [ ] docs/auth-gateway/frontend/design.md names the hub exception and links the brand book for theme and chrome.
```
