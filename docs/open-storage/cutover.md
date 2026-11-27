# Cutover

AS IS of the planners in [open-storage-cutover](../../scripts/open-storage-cutover/). 

The tools plan and compare fixtures. They do not run `pg_dump`, `pg_restore`, `psql`, `mc`, a DNS change, or decommission. No dump has been taken by this change. Counts are queries the operator would run; this page records none.

Run a plan with `PYTHONPATH=scripts/open-storage-cutover python -m cutover.cli <command>`. Exit `2` means the plan was refused.

## Dump and restore

`plan-dump` prints three commands, in order: `pg_dump -Fc -d db_storage`, `pg_restore` into database `db_storage` on host `postgres`, then `TRUNCATE TABLE upload_sessions`. It refuses the plan when the legacy app is not stopped. `upload_sessions` is restored empty: the table stays, its rows are not carried. The baseline queries name `users`, `file_records` (by `status` and `section`), `user_quota_usage`, `file_index_links` (by `state`), and `upload_sessions`. They are printed, not executed.

## Bucket

`plan-mirror` prints `mc mirror --preserve legacy/storage namespace/storage` for endpoint URLs, then `mc ls --recursive --summarize` for both aliases. A host path, including `/media/aleksey/HardDisk/minio`, is refused. The copy is not `cp` and does not carry MinIO `xl.meta` by hand. `compare_listings` matches object count and total bytes. The target listing must include the prefixes `users/`, `shared/`, `files/`, and `_meta/`.

## Rows and objects

`verify_committed` takes COMMITTED `file_records` (`relative_path`, `size_bytes`) and object listings. A missing object, an extra object, and a size that differs from `size_bytes` are each reported. Pass is zero of each and equal counts.

## Quotas

`reconcile_quotas` sets `total_bytes` to the sum of committed `size_bytes` for that user, `private_bytes` to the committed `PRIVATE` sum, and `photos_bytes` to the committed `PHOTOS` sum. `FILES`, `SHARED`, `RESUMES`, and `GENERATED` add only to `total_bytes`. `PENDING` and `DELETED` add nothing. The function does not call the app.

The admin route in code is `GET /api/admin/maintenance/run`. It calls `MaintenanceService.reconcile_quotas`, which rewrites `total_bytes` only when the absolute gap is greater than `QUOTA_MISMATCH_THRESHOLD_BYTES` (1000000) and does not recompute `private_bytes` or `photos_bytes`. The story text says `POST`; the route is GET.

## Subjects

A JSON object maps each current `users.id` to an idp subject. `apply_subject_switch` requires that map to be one-to-one with the current ids: a duplicate target, an unmapped id, or a key that is not a current id is refused. A second apply of the same file is refused because those ids are no longer `users.id`. The SQL rewrites `users.id` in place and the `user_id` columns of `file_records`, `user_quota_usage`, `file_index_links`, and `upload_sessions`. It does not `INSERT` a user and it does not change the column type. The statements are tested on SQLite with text ids. They are not run against PostgreSQL here, and a uuid column will not accept a non-uuid literal. After the rewrite every `users.id` is the mapped subject and the row count is the same.

`get_current_user` reads `X-Auth-Subject`. A non-UUID subject is not inserted. `upsert_from_principal` inserts a `users` row when that subject is a UUID the table does not already hold. The subject map still has to be applied before a login that would create a second `users` row. This page does not change that code.

## RAG

`claim_due` in [file_index_link_repo.py](../../src/open-storage/app/app/infrastructure/database/repositories/file_index_link_repo.py) keeps a row only when all three hold:

- `state` is in `PENDING`, `SUBMITTED`, `REMOVED`, `REINDEX_PENDING` (`DUE_INDEX_STATES` in [indexing.py](../../src/open-storage/app/app/domain/indexing.py))
- `section` is not `PRIVATE`
- `next_attempt_at` is null or `<=` the claim time

`INDEXED`, `FAILED`, and `SKIPPED` are outside the state filter, so they are not claimed. A future `next_attempt_at` is not claimed either. That is the exclusion that can empty a search page while the bytes are still there.

`plan-requeue` sets every non-`PRIVATE` row except `REMOVED` to `PENDING` with `next_attempt_at` null and `attempts` 0. `REMOVED` stays `REMOVED` with `next_attempt_at` null. `rag_file_id` is not in the `UPDATE`. `PRIVATE` is left as it is. The planner refuses `RAG_ENABLED=true`. The printed value is `RAG_ENABLED=false`. [deploy/open-storage/.env.example](../../deploy/open-storage/.env.example) already sets `RAG_ENABLED=false`.

## Rollback

The old stack's volumes stay. The proxy block and the gateway host block are reverted from git. The new namespace volumes are not wiped.

## Decommission review

Not a command. The decommission checklist: the rollback window has passed, the dump and the bucket copy are still readable, and only then are the old containers and volumes removed. `~/projects/WebStorage` is archived or removed with a pointer at this repository. The live database and bucket are the [common](../common/init.md) services (`postgres`, bucket `storage` on `minio`). They stay. `mlflow` and the other buckets stay.
