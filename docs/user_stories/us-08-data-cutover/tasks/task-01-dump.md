# task-01 Dump

Story: [US-08](../init.md)

## Outcome

A consistent dump of `db_storage` exists, taken with the legacy stack stopped, plus the pre-cutover counts it is checked against.

## Paths

- Operator host: `~/backups/storage-cutover/` (outside git)

## Done when

The legacy app is stopped before the dump; `pg_dump -Fc` of `db_storage` completes and `pg_restore -l` lists every table; the dump's checksum is recorded; counts for `users`, `file_records` (split by `status` and `section`), `user_quota_usage` and `file_index_links` (split by `state`) are recorded as the baseline; `upload_sessions` is counted and recorded.
