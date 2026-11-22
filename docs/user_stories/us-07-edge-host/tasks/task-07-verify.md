# task-07 Prove the host

Story: [US-07](../init.md)

## Outcome

The host is proven for anonymous, family, admin, stranger and blocked, the way `make verify` proves the other hosts, and the result is recorded.

## Paths

- `scripts/` — the verify script, if the other hosts are checked there
- `docs/open-storage/` — the namespace doc that links the result

## Done when

For each of anonymous, family, admin, stranger and blocked, the request and its status and body are recorded: `/health` 200 anonymous; `/` and `/api/files` 200 for family and admin; `403 forbidden` for stranger; `403 blocked` for blocked; a 401 body from `/api/*` anonymous is the gateway's `{"error":"unauthorized"}`, not the app's; a large download past 60s is timed and recorded.
