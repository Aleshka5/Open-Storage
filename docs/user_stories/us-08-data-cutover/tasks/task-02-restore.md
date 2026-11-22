# task-02 Restore

Story: [US-08](../init.md)

## Outcome

The dump is restored into the namespace's own postgres, and the app reaches it by service name.

## Paths

- `open-storage-postgres`
- `deploy/open-storage/.env.example` — `DATABASE_URL` shape

## Done when

`pg_restore` into the empty database completes with no error; `alembic upgrade head` reports no pending revision because the dump already carries the schema; `psql` from `open-storage-app` to `open-storage-postgres` works with the env file's values; the table counts equal the baseline from [task-01](task-01-dump.md).
