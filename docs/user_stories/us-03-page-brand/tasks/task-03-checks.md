# task-03 Checks and the design note

Story: [US-03](../init.md)

## Outcome

The brand book’s check list that this page can lock is locked by tests, and the design note points at the brand book for the facts this story uses.

## Paths

- `src/auth-gateway/resume-page/src/`
- `docs/auth-gateway/frontend/design.md`

## Done when

- Tests lock: the preference fallback, `system` following `prefers-color-scheme`, both faces on the button and banner classes, `--accent` unused as text color, and the theme control’s name and three labels.
- `npm test` and `npm run build` pass, inside the 95 KB initial JS budget.
- [design.md](../../../auth-gateway/frontend/design.md) states that this page is the hub (owl tab icon, diamond header mark) and that theme and chrome follow the [brand book](../../../brand-book/init.md). It does not copy the palette.
