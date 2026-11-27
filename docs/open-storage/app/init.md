# app — init

The storage service. One FastAPI process that owns every byte and every row of the namespace, serves the API, and serves the built SPA. What it needs from outside itself is in the [external contract](external-contract.md); its endpoints are in the [API contract](api-contract.md); who may call it is in the [namespace page](../init.md).

FastAPI application `HomeCloud`, version `1.0`, entrypoint `main:app`. Container port `8000`, which is the `storage` upstream of the gateway. It publishes no host port.

## Purpose and bounded contexts

| Context | Owns | Code |
|---|---|---|
| Files | One tree per user with folders, rename, ZIP upload, folder download | `application/file_service.py` |
| Shared | One tree for the family, `shared/…`, same operations | `FileService` with `FileSection.SHARED` |
| Photos | Gallery with generated JPEG previews, paging, original download | `application/photo_service.py` |
| Private vault | AES-256-GCM over content and names, unlocked by a passphrase per session | `application/private_service.py`, `infrastructure/storage/encrypted_adapter.py` |
| Keys registry | One flat `Keys/keys.yaml` inside the vault | `application/keys_registry_service.py` |
| Resumes | Country → company → vacancy tree, `meta.yaml` per vacancy, `statuses.yaml` | `application/resume_service.py` |
| Generated images | Read-only history of image-generation runs (`POST` is written by the generator) | `application/generated_service.py` |
| Quota | Denormalised per-user usage and limits, checked on upload, reconciled hourly | `application/file_service.py`, `maintenance_service.py` |
| Admin | Users, quotas, block, delete, bucket stats and health | `application/admin_service.py` |
| Indexing | Queue of keys to register in RAG, plus photo search | `application/indexing/` |
| Operations | `pg_dump` backup to the bucket, stale-record and `.tmp` cleanup | `application/backup_service.py`, `maintenance_service.py` |

The API groups by section, not by context: `/api/files` and `/api/shared` run the same handlers on different section roots, and `/api/resumes/files` runs them through a factory (`presentation/routers/file_router_factory.py`).

## Layers

`backend/app/`, in the legacy tree; the paths below are relative to the service source that moves to `src/open-storage/app/`.

| Layer | Directory | Contents | May depend on |
|---|---|---|---|
| Domain | `domain/` | `FileRecord`, `User`, `AuthPrincipal`, `DiskVolume`, `FileSection`/`FileStatus`, `Role`, `StorageQuota`, `ErrorCode`, the index-target decision, domain exceptions | nothing |
| Application | `application/` | Section services, `AdminService`, `MaintenanceService`, `BackupService`, `indexing/`, and ports (`ports/rag_index.py`, `ports/index_links.py`) | domain |
| Infrastructure | `infrastructure/` | `S3StorageAdapter`, `EncryptedStorageAdapter`, `DiskRouter`, `ThumbnailService`, repositories, DB session, `SessionStore` (Redis), `RagIndexClient`. No User-Service client | domain, application ports |
| Presentation | `presentation/` | Routers, pydantic schemas, FastAPI dependencies, `check_role`, `AuthRateLimitMiddleware`, exception handlers, `indexing_notify` | application |

Two rules the code keeps: the presentation layer wires HTTP to application services and never touches an adapter, and encryption exists only as a decorator of a `StorageAdapter`, so no plain-section code can see a private key. `application/` also imports two concrete clients it does not own — `infrastructure.rag.client` and `infrastructure.database.repositories.*` — so the arrow from application to infrastructure exists in the import graph, and only the direction infrastructure → application is absent.

Errors are one envelope for every handler: `{"detail": {"error_code": "<CODE>", "message": "<text>"}}`, with `available_bytes` on `413 QUOTA_EXCEEDED` and `retry_after` on `429 TOO_MANY_ATTEMPTS`.

## Database

One database, `db_storage`, owner role `storage`, PostgreSQL, SQLAlchemy 2 async over `asyncpg`. The container entrypoint runs `alembic upgrade head` before the process starts; an invalid migration stops the container.

| Table | Rows are | Owner in code | Key constraints |
|---|---|---|---|
| `users` | The local projection of a caller: `id`, `email`, `is_active`, `created_at` | `UserRepository`, written by `get_current_user` on every request | `email` unique, `id` = the identity key |
| `file_records` | One row per stored object: `disk_id`, `relative_path` (the disk-relative key), `original_name`, `size_bytes`, `mime_type`, `is_encrypted`, `section`, `status`, `checksum_sha256`, `created_at`, `last_accessed_at` | `FileRepository` through `FileService` | FK `user_id` → `users.id` `ON DELETE CASCADE`; `section` and `status` are native PG enums |
| `user_quota_usage` | One row per user: `total_bytes`, `limit_bytes`, `private_bytes`, `private_limit_bytes`, `photos_bytes`, `updated_at` | `QuotaRepository` | PK = FK `user_id` |
| `file_index_links` | One row per record that is, was, or should be indexed: `s3_key`, `content_sha256`, `content_type`, `rag_file_id`, `state`, `attempts`, `next_attempt_at`, `last_error_code` | `FileIndexLinkRepository` through `application/indexing/` | `file_record_id` unique and `ON DELETE SET NULL`; `rag_file_id` unique |
| `upload_sessions` | Nothing. The model and table exist; no repository, route or service reads or writes them. | — | FK `user_id` |

Enums: `file_section` = `PHOTOS`, `FILES`, `PRIVATE`, `SHARED`, `RESUMES`, `GENERATED` (`006`, `007` add values with `ALTER TYPE … ADD VALUE` outside a transaction); `file_status` = `PENDING`, `COMMITTED`, `DELETED` (`009` rebuilds the type and refuses to run while an `ARCHIVED` row exists). The legacy field `users.role` no longer exists (`005`); the role is computed per request.

`get_current_user` reads the five v1 headers. The contract is [identity v1](../../auth-gateway/external-contracts/identity-v1.md). The User-Service client is gone. `users.id` is still a UUID column, so a non-UUID subject is not inserted. Every other table reaches a user through `users.id`, so a change of identity scheme is a data migration, not a code change.

## Storage layout in MinIO

One bucket, `S3_BUCKET` (default `storage`), S3 API, path-style addressing. Keys are POSIX paths under the bucket root and have exactly one writer: this service. `file_records.relative_path` holds the same key, so the database and the bucket name the same thing.

Directories are real: an empty folder is a zero-byte object whose key ends with `/`.

| Prefix | Contents | Section |
|---|---|---|
| `users/{user_id}/files/…` | User files | `FILES` |
| `users/{user_id}/.tmp/{record_id}` | Upload staging, renamed to its final key before commit | any user section |
| `users/{user_id}/photos/originals/{id}{ext}` | Photo originals, up to 7 extensions | `PHOTOS` |
| `users/{user_id}/photos/previews/{id}_thumb.jpg` | JPEG preview, longest edge `THUMBNAIL_MAX_PX` (400) | `PHOTOS` |
| `users/{user_id}/private/…` | Ciphertext, names encrypted too, plus `.marker` (decrypts to `HOMECLOUD_MARKER_V1`) | `PRIVATE` |
| `users/{user_id}/resumes/{country}/{company}/{vacancy}/…`, `…/meta.yaml`, `users/{user_id}/resumes/statuses.yaml` | Resume tree and its two YAML documents | `RESUMES` |
| `users/{user_id}/generated/{run_id}/meta.yaml`, `result.png`, `ref-N.png` | One generation run, `run_id` = `YYYYmmddTHHMMSSZ-xxxxxxxx` | `GENERATED` |
| `shared/…` | Family tree | `SHARED` |
| `_meta/backups/db_backup_YYYY-MM-DD_HH-MM-SS.sql.zst` | Compressed `pg_dump`, retention 30 days | — |

A key is a contract with RAG: `file_index_links.s3_key` is the key RAG reads, so a layout change is a change to the [external contract](external-contract.md#rag-edge) in the same release.

Retention is not a feature: deleted objects leave immediately, and the only garbage collector is the scheduled `.tmp` sweep.

## Scheduled jobs

APScheduler inside the process (`lifespan` in `main.py`). A second replica would run every job twice; the `index_sync` tick is the only one with a lock.

**The build is broken here, not just the docs.** `lifespan` only calls `scheduler.add_job` once, for `index_sync`. The four jobs the log line and every legacy doc promise are not registered:

| Job | Promised schedule (`docs/Design Spec.md` §5) | Registered? | Code that exists |
|---|---|---|---|
| `index_sync` | every `RAG_SYNC_INTERVAL_SECONDS` (60) when `RAG_ENABLED`, `max_instances=1`, `coalesce`, in-process lock | yes | `application/indexing/sync_job.py` — one page of due links: register, poll, re-key, delete vectors |
| `cleanup_pending` | hourly | **no** | `MaintenanceService.cleanup_pending_records` — hard-deletes `PENDING` rows after 1 h and their staging objects |
| `cleanup_tmp` | hourly | **no** | `MaintenanceService.cleanup_tmp_dirs` — deletes staging entries older than 1 h under every `…/.tmp/` prefix |
| `reconcile_quotas` | hourly | **no** | `MaintenanceService.reconcile_quotas` — rewrites `total_bytes` when the drift exceeds 1 MB |
| `db_backup` | daily 02:00 | **no** | `BackupService.run_db_backup` — `pg_dump`, zstd level 19, 30-day retention |

All four run only when an admin calls `GET /api/admin/maintenance/run` (the first three) or `GET /api/admin/backup/run` (backup). Startup also calls one non-scheduled step: `backfill(links)` once when `RAG_ENABLED`, which writes nothing unless `RAG_BACKFILL_ENABLED`. The startup log line `APScheduler started: db_backup@02:00, cleanup_pending@1h, cleanup_tmp@1h, reconcile_quotas@04:00` reports jobs that were never added, and `reconcile_quotas` is called hourly in reality, not at 04:00.

## Properties to keep

- **One writer per key.** The app writes and deletes objects; RAG reads them; the image generator `POST`s and never writes the bucket.
- **Two-step store.** A record is created `PENDING`, the object is written under `.tmp/` and renamed, and only then the row becomes `COMMITTED`. A committed row has an object.
- **Quota is denormalised.** Every upload checks `user_quota_usage` before the first byte and charges the size; the hourly reconcile is the repair.
- **Private bytes never leave the vault.** `PRIVATE` and encrypted records raise in the index-target decision and get no `file_index_links` row.
- **SQLite and a second app are not options.** The single database, single process and in-process scheduler are the shape today.

## Configuration

`config.py`, one `Settings` object from `pydantic-settings` on `.env` / process env, cached with `lru_cache`. Env names and defaults are owned by `deploy/open-storage/.env.example`; the groups are `database`, `cache_db`, `storage`, `s3`, `auth` (vault TTL only), `business_logic`, `logging`, `spa`, `rag`. There is no `user_service` group and no `AUTH_COOKIE_NAME`.

## Requiring an operator answer

Recorded, not decided:

1. `users.id` is still a UUID column. The reader uses `X-Auth-Subject` ([identity v1](../../auth-gateway/external-contracts/identity-v1.md)). A non-UUID subject is not inserted. Which existing rows map to idp subjects is [cutover.md](../cutover.md).
2. The four unregistered jobs: are they meant to schedule, or is the hourly claim in every legacy doc the error? The code cannot answer.
3. `.tmp` staging under `users/{user_id}/.tmp/` vs. the documented `…/files/.tmp/`: whether the current placement is intended or a path-join bug is not decidable from the code alone.
