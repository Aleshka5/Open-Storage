> **ID:** US-08
> **Status:** TODO
> **Specs:** [US-05](../us-05-storage-namespace/init.md), [US-06](../us-06-identity-v1/init.md), [US-07](../us-07-edge-host/init.md)

## Overview

The data moves from the shared stack into the namespace's own postgres and minio, and users switch to the new host. The legacy database is `db_storage` owned by role `storage`; the tables are `users`, `file_records`, `user_quota_usage`, `upload_sessions`, `file_index_links`. The blobs are one bucket `storage` with keys `users/<uid>/<section>/…`, `shared/…`, `files/…` and `_meta/…`, on the host path `/media/aleksey/HardDisk/minio`. RAG indexing is the hazard: a due-queue predicate that silently excludes rows empties a page while the bytes survive, so RAG runs off until a separate re-queue proves the rows come back.

Tasks: [dump](tasks/task-01-dump.md), [restore](tasks/task-02-restore.md), [copy the bucket](tasks/task-03-bucket.md), [verify](tasks/task-04-verify.md), [quotas](tasks/task-05-quotas.md), [switch users](tasks/task-06-switch.md), [re-queue RAG](tasks/task-07-rag-requeue.md), [decommission](tasks/task-08-decommission.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The dump is `pg_dump` of `db_storage` and the restore is into the namespace's own postgres. No shared database survives for this app. | Pointing the namespace's postgres at the shared host and calling that "owned" |
| D2 | The bucket is copied with `mc mirror` between two MinIO endpoints, not `cp -r` on the host directory. The on-disk form is MinIO's `xl.meta` layout, not one file per object. | A filesystem copy, which silently carries MinIO's internal metadata and breaks on a version mismatch |
| D3 | The cutover stops the legacy stack before the dump, so no row and no object is written during the copy. | A live dump with a stop-time delta reconciliation nobody wrote |
| D4 | RAG runs with `RAG_ENABLED=false` until the links are re-queued and proven. RAG is not part of the cutover. | Cutting over with indexing on and discovering the empty search page later |
| D5 | Verification is per row and per object: row counts and ids match, and each object's stored `size_bytes` matches the object's size in the new bucket. | "Data is migrated" as the criterion |
| D6 | The rollback is the old stack started again from intact volumes, with the proxy block and the gateway host block reverted from git. The new namespace's volumes are kept, not wiped, so a second attempt is cheap. | Deleting the new volumes on a failed attempt |
| D7 | The subject is the new idp's `sub`, so the app's projection rule meets a UUID mismatch for every existing user. The cutover decides it once, in one step, with the old ids mapped to subjects. | Letting the app mint new user rows on first login, which orphans every old `users.id` and its `file_records` |
| D8 | `upload_sessions` is not carried. No repository, route or service reads or writes it today — it is a model and a table with no code behind it — so its rows cannot represent an upload in flight. The table is carried empty. | Carrying rows for a table no code reads, which makes the verify step compare a number nobody can act on |

## Goals

- Every committed row and every object exists in the new namespace.
- Quotas match the committed bytes.
- Search comes back only after a proven re-queue, not as a side effect.

## Non-goals

- New features.
- RAG re-index changes beyond the re-queue.
- The MVP stand.
- Idp key rotation, or preserving old UUIDs ([US-01](../../user_stories/us-01-identity-edge/init.md) already refused them).

## User Story

**As** a family member, I want my photos, files, resumes and vault to be unchanged after the move, so that the new host is the same archive, not a second one.

**Acceptance**

- `psql` on the new database reports the same row counts for `users`, `file_records`, `user_quota_usage` and `file_index_links` as the dump's pre-cutover counts. `upload_sessions` is empty on both sides.
- Every `users.id` after the migration is a subject the idp issues, and each maps one-to-one to one pre-cutover `users.id` through the mapping this task records. A first login after cutover creates no new `users` row.
- For the operator account, a listing of each section returns the same ids, names and sizes as the old stack.
- `mc stat` for every key in `file_records` finds the object and its size equals `size_bytes`; the count of `file_records` rows with `status = 'COMMITTED'` equals the count of found objects.
- `user_quota_usage.total_bytes` equals the sum of committed `size_bytes` per user after reconciliation.
- The encrypted vault unlocks with the same passphrase and lists the same private entries.
- `curl -fsS https://storage.filenkov.store/api/photos/search?q=…` answers `503` with `INDEXING_UNAVAILABLE` while `RAG_ENABLED=false`, and the same query answers results after the re-queue task.
- A user who logs in twice gets a new vault session and the same files.

## Definition of Done

- [ ] Counts, per-section listings, object sizes and quotas are recorded with the commands.
- [ ] The old stack is stopped with its volumes intact, and the rollback is written.
- [ ] RAG is off, with the re-queue tracked as its own task and not marked done here.
- [ ] The decommission task has its own review point.
