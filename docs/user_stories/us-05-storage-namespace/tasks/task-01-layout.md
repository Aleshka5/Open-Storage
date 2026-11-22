# task-01 Repository layout

Story: [US-05](../init.md)

## Outcome

The app, the SPA and the deploy files sit at the paths [repository-layout.md](../../../repository-layout.md) names, and nothing points at a sibling checkout.

## Paths

- `src/open-storage/app/` — the FastAPI app, `tests/` inside it
- `src/open-storage/spa/` — the Vite SPA
- `deploy/open-storage/`

## Done when

`src/open-storage/app/tests/` holds the same files the legacy `backend/tests` did, the SPA builds from `src/open-storage/spa`, and no path in the tree resolves outside `~/projects/Open-Storage`.
