# task-11 Resume page

Story: [US-01](../init.md)

## Outcome

The showcase matches [frontend/design.md](../../../frontend/design.md), [security.md](../../../frontend/security.md), and [backend-contract.md](../../../frontend/backend-contract.md). Nodes come from `import.meta.glob`. `useSession` calls `/auth/session` once. `/admin` is a table with no pagination. Bundle budget is 95 KB. nginx uses `try_files`.

## Paths

- `src/auth-gateway/resume-page/`

## Done when

`npm run build` fails on a registry invariant or on a bundle over 95 KB. `npm test` passes. A deep URL returns `index.html`.
