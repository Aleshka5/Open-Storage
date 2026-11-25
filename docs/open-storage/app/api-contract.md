# app — API contract

Every endpoint this service answers, and nothing else. Enumerated from the live application: importing `main:app` and reading `app.openapi()` yields **87 operations on 75 paths** — 85 operations from `presentation/routers/*.py`, plus `GET /health` and `GET /` in `main.py`. Every one has a row below: auth 7, quota 1, files 9, shared 9, photos 5, private 15, resumes 9 + resumes-files 9, generated 5, indexing 5, admin 11, service 3 — the third is the SPA catch-all, listed under service and excluded from the 87.

Not listed: FastAPI's own `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, and the SPA catch-all (`GET /{full_path:path}`, `main.py`) that serves `/opt/spa`. They are the framework and the [SPA](../spa/init.md), not the product API.

## Conventions

| Topic | Rule |
|---|---|
| Base | Same origin as the SPA. No prefix in front of `/api`. |
| Caller | The gateway, with [identity v1](../../auth-gateway/external-contracts/identity-v1.md) headers. "Auth: user" below means every one of the five identity headers as the app reads them today; "Auth: role" adds the app's storage-role gate. |
| Error body | `{"detail": {"error_code": "<CODE>", "message": "<text>"}}`, plus `available_bytes` on `413` and `retry_after` on `429`. Never the edge's `{"error": …}`. |
| Identity failures, every route | no `X-Auth-Subject` → `401 UNAUTHORIZED` and no `users` row; missing or unknown `X-Auth-Roles` → `STRANGER`; blocked → `403 ACCESS_DENIED` |
| Paths | Query or JSON body. `/` prefix accepted, `\` folded to `/`, `..` refused (`PATH_TRAVERSAL_DETECTED`) |
| Empty success | `204` |

Role gates in code: `check_role(Role.FAMILY, Role.ADMIN)` for `/api/shared/**` and every `/api/resumes/**` route, `check_role(Role.ADMIN)` for `/api/admin/**`, `/api/admin/indexing/**` and `/api/admin/indexing/backfill|retry`. Everything else is "user". A wrong role is `403 ACCESS_DENIED`.

## auth — `/api/auth`, tag `auth`

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `POST` | `/register` | Retired identity endpoint | — | `410` | always `410 UNAUTHORIZED` "retired" |
| `POST` | `/login` | Retired | — | `410` | always `410` |
| `GET` | `/google` | Retired | — | `410` | always `410` |
| `GET` | `/google/callback` | Retired | — | `410` | always `410` |
| `GET` | `/google/session` | Retired | — | `410` | always `410` |
| `POST` | `/logout` | Retired; logout is the gateway's | — | `410` | always `410 ACCESS_DENIED` |
| `GET` | `/me` | The caller as the app sees them: Auth user | — | `200 {user_id, email, role}` with `role` in `STRANGER`/`FAMILY`/`ADMIN`/`BLOCKED` | identity failures above |

`/me` is the SPA's session probe. The six retired routes (`/register`, `/login`, the three `/google*`, `/logout`) exist so an old client gets a clear answer instead of `404`.

## quota — `/api/quota`, tag `quota`

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `/me` | Total and private usage and limits; creates the row on first read | — | `200 {used_bytes, limit_bytes, private_bytes, private_limit_bytes}` | identity failures |

`limit_bytes = 0` means unlimited. The value is the per-user cap, not free bucket space.

## files — `/api/files`, tag `files`

Section root `users/{user_id}/files`, section `FILES`. All routes: Auth user; `503 DISK_UNAVAILABLE` when no bucket passes the free-space probe.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `""` | List one folder | Query `path` (default `/`) | `200 [FileNode]` | `404 FILE_NOT_FOUND` (folder missing) |
| `POST` | `/upload` | Store one file, overwriting the same name | Query `path`; multipart part `file` | `201 FileRecord` | `400 UNSUPPORTED_FORMAT` (no filename), `400 PATH_TRAVERSAL_DETECTED`, `413 QUOTA_EXCEEDED` |
| `POST` | `/upload-zip` | Unpack a `.zip` folder into `path` | Query `path`; multipart part `file` (`.zip`) | `201 {files, dirs, total_bytes}` | `400 UNSUPPORTED_FORMAT` (not a zip, empty zip, absolute or `..` entry), `413 QUOTA_EXCEEDED` (uncompressed size) |
| `GET` | `/download` | Stream one file | Query `path` | `200` stream, `Content-Disposition: attachment` | `404 FILE_NOT_FOUND` |
| `GET` | `/download-folder` | Stream a folder as zip | Query `path` | `200 application/zip` | `404 FILE_NOT_FOUND` |
| `DELETE` | `""` | Delete a file or a folder | Query `path` | `204` | `404 FILE_NOT_FOUND`; a `FILES` folder is deleted record-by-record |
| `POST` | `/mkdir` | Create a folder | JSON `{path, name}` (`name` ≥ 1 char) | `201 {path, name}` | `400 PATH_TRAVERSAL_DETECTED`, `422` (schema) |
| `PATCH` | `/rename` | Rename a file or a folder | JSON `{path, new_name}` | `200 FileRecord` (file) or `204` (folder) | `404 FILE_NOT_FOUND`, `400 PATH_TRAVERSAL_DETECTED` |
| `GET` | `/search` | Reserved | Query `q` (≥ 1 char) | — | always `501 NOT_IMPLEMENTED` |

`FileNode` = `{name, is_dir, size, modified_at, path, uploaded_by}`; `FileRecord` = `{id, name, size, section, status, created_at}`. `uploaded_by` is filled only in `SHARED`.

## shared — `/api/shared`, tag `shared`

Section root `shared`, section `SHARED`. Auth role: FAMILY or ADMIN. The nine routes are the same handlers as `files` on a different root.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `""` | List the family tree; nodes may carry `uploaded_by` | Query `path` | `200 [FileNode]` | `403 ACCESS_DENIED`, `404 FILE_NOT_FOUND` |
| `POST` | `/upload` | Store one file in the shared tree | Query `path`; part `file` | `201 FileRecord` | `413 QUOTA_EXCEEDED`, `400 …` |
| `POST` | `/upload-zip` | Unpack a zip into the shared tree | Query `path`; part `file` | `201 {files, dirs, total_bytes}` | `413 QUOTA_EXCEEDED`, `400 …` |
| `GET` | `/download` | Stream one shared file | Query `path` | `200` stream | `404 FILE_NOT_FOUND` |
| `GET` | `/download-folder` | Stream a shared folder as zip | Query `path` | `200 application/zip` | `404 FILE_NOT_FOUND` |
| `DELETE` | `""` | Delete a shared path | Query `path` | `204` | `403 ACCESS_DENIED` (not owner, not admin, and the record was found), `404 FILE_NOT_FOUND` |
| `POST` | `/mkdir` | Create a shared folder | JSON `{path, name}` | `201 {path, name}` | `422` |
| `PATCH` | `/rename` | Rename in the shared tree | JSON `{path, new_name}` | `200 FileRecord` or `204` | `404 FILE_NOT_FOUND` |
| `GET` | `/search` | Reserved | Query `q` | — | always `501 NOT_IMPLEMENTED` |

## photos — `/api/photos`, tag `photos`

Section root `users/{user_id}/photos`, section `PHOTOS`. Extensions `.jpg .jpeg .png .webp .gif .heic .heif`.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `""` | Page of the caller's photos, newest first | Query `page` ≥ 1 (default 1), `limit` ≥ 1 (default `PHOTO_BATCH_SIZE` 30) | `200 {items: [PhotoItem], total, has_next}` | `400 UNSUPPORTED_FORMAT` |
| `POST` | `/upload` | Store the original; the 201 follows that commit, and the JPEG preview and index notify are not on that wait | Multipart `file` | `201 PhotoItem` | `400 UNSUPPORTED_FORMAT` (extension), `400 PATH_TRAVERSAL_DETECTED`, `413 QUOTA_EXCEEDED` |
| `GET` | `{photo_id}/preview` | JPEG preview (generated on first read if absent) | Path `photo_id` (UUID) | `200 image/jpeg` | `404 FILE_NOT_FOUND`, `400 UNSUPPORTED_FORMAT` |
| `GET` | `{photo_id}/original` | Stream the original | Path `photo_id` | `200` stream with original mime | `404 FILE_NOT_FOUND` |
| `DELETE` | `{photo_id}` | Delete original, preview, row, quota | Path `photo_id` | `204` | `404 FILE_NOT_FOUND` |

`PhotoItem` = `{id, preview_url, original_url, created_at, size}`.

## private — `/api/private`, tag `private`

The encrypted vault, section root `users/{user_id}/private`, section `PRIVATE`. The Redis key is `private_key:` plus the SHA-256 hex of the `__Secure-open_session` cookie, for `PRIVATE_SESSION_TTL_HOURS` (4). The raw cookie is not the key.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `POST` | `/unlock` | Derive the key from the passphrase, check or write `.marker`, store the key for the session | JSON `{passphrase}` (≥ 1) | `200 {success: true}` / `200 {success: false}` | `401 UNAUTHORIZED` (no session cookie), `429 TOO_MANY_ATTEMPTS` + `retry_after` (5 failures per user+IP per 900 s) |
| `POST` | `/lock` | Forget the key for this session | Session cookie | `204` | `401 UNAUTHORIZED` (no cookie). **No user check** — see the [namespace findings](../init.md#mismatches-with-the-legacy-project) |
| `POST` | `/reset` | Wipe the whole vault (used when the passphrase is lost) | Session cookie | `204` | `403 ACCESS_DENIED` unless the unlock limit is already reached, `401 UNAUTHORIZED` |
| `GET` | `/quota` | Private usage and private cap | — | `200 {private_bytes, private_limit_bytes}` | identity failures |
| `GET` | `/session` | Is this session unlocked | Session cookie | `200 {active, expires_in_seconds}` | `401 UNAUTHORIZED` (no cookie) |
| `GET` | `/keys` | Read `Keys/keys.yaml`, creating folder and file on first read | — | `200 {keys: [{name, value}]}` in file order | `401 PRIVATE_SESSION_EXPIRED` (no key), `409 KEYS_YAML_INVALID` (file not a flat map; not rewritten) |
| `PUT` | `/keys` | Replace the whole file | JSON `{keys: [{name, value}]}` | `200 {keys: […]}` in the order sent | `401 PRIVATE_SESSION_EXPIRED`, `400 KEY_NAME_EMPTY` / `KEY_VALUE_EMPTY` / `KEY_NAME_DUPLICATE` |
| `GET` | `""` | List a vault folder | Query `path` | `200 [FileNode]` | `401 PRIVATE_SESSION_EXPIRED`, `404 FILE_NOT_FOUND` |
| `POST` | `/upload` | Store into the vault (private cap and total cap both checked) | Query `path`; part `file` | `201 FileRecord` | `401 PRIVATE_SESSION_EXPIRED`, `413 QUOTA_EXCEEDED`, `400 …` |
| `GET` | `/download` | Stream one vault file | Query `path` | `200` stream | `401 PRIVATE_SESSION_EXPIRED`, `404 FILE_NOT_FOUND` |
| `DELETE` | `""` | Delete a vault path | Query `path` | `204` | `401 PRIVATE_SESSION_EXPIRED`, `404 FILE_NOT_FOUND` |
| `POST` | `/mkdir` | Create a vault folder | JSON `{path, name}` | `201 {path, name}` | `401 PRIVATE_SESSION_EXPIRED` |
| `PATCH` | `/rename` | Rename in the vault | JSON `{path, new_name}` | `200 FileRecord` or `204` | `401 PRIVATE_SESSION_EXPIRED`, `404 FILE_NOT_FOUND` |
| `GET` | `/search` | Reserved | Query `q` | — | `401 PRIVATE_SESSION_EXPIRED`, else `501 NOT_IMPLEMENTED` |
| `GET` | `/download-folder` | Stream a vault folder as zip (plain `Content-Disposition`, no RFC 6266 encoding) | Query `path` | `200 application/zip` | `401 PRIVATE_SESSION_EXPIRED`, `404 FILE_NOT_FOUND` |

Every file route above except `lock`, `session` and `unlock` also requires Auth user. `_get_session_id` raises `401 UNAUTHORIZED`, not `PRIVATE_SESSION_EXPIRED`, when the cookie is absent; `PRIVATE_SESSION_EXPIRED` is raised by the vault service when the cookie is present but Redis has no key.

## resumes — `/api/resumes`, tag `resumes`, and `/api/resumes/files`, tag `resumes-files`

Section root `users/{user_id}/resumes`, section `RESUMES`. `path` is relative to that root: `""` = countries, `{country}`, `{country}/{company}`, `{country}/{company}/{vacancy}`. Auth role: FAMILY or ADMIN on every route.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `/tree` | List one tree level | Query `path` (default `""`) | `200 {path, level, items: [ResumeNode]}` | `400 RESUME_DEPTH_INVALID`, `404 FILE_NOT_FOUND` |
| `POST` | `/tree` | Create a country, company or vacancy (a vacancy also gets `meta.yaml`) | JSON `{path="", name, status_id?}` | `201 ResumeNode` | `400 RESUME_NAME_INVALID` / `RESUME_DEPTH_INVALID` / `RESUME_STATUS_INVALID`, `409 RESUME_NODE_EXISTS` |
| `PATCH` | `/tree` | Rename a node | JSON `{path, new_name}` | `200 ResumeNode` | `400 RESUME_NAME_INVALID`, `409 RESUME_NODE_EXISTS`, `404 FILE_NOT_FOUND` |
| `DELETE` | `/tree` | Delete a node and every descendant | Query `path` | `204` | `400 RESUME_DEPTH_INVALID`, `404 FILE_NOT_FOUND` |
| `GET` | `/vacancy` | Read a vacancy's `meta.yaml` | Query `path` | `200 VacancyMeta` | `400 RESUME_DEPTH_INVALID`, `404 FILE_NOT_FOUND`, `409 RESUME_META_INVALID` |
| `PUT` | `/vacancy` | Replace a vacancy's metadata | Query `path`; JSON `{website_url, status_id?, fields: [{name, value}]}` | `200 VacancyMeta` | `400 RESUME_FIELD_INVALID`, `409 RESUME_META_INVALID` |
| `GET` | `/vacancies` | Every vacancy in the tree, sorted | — | `200 {items: [VacancyListItem]}` | — |
| `GET` | `/statuses` | Status list; seeds Applied/Interview/Offer/Rejected on first read | — | `200 {statuses: [ResumeStatus]}` | `409 RESUME_META_INVALID` |
| `PUT` | `/statuses` | Replace the status list | JSON `{statuses: [{id?, name, color}]}` | `200 {statuses: […]}` | `400 RESUME_STATUS_INVALID` |

`ResumeNode` = `{name, path, level, child_count, modified_at, status_id?, website_url?}`; `VacancyMeta` = `{path, name, website_url, status_id, fields}`; `ResumeStatus` = `{id, name, color}`. A non-empty `website_url` without a scheme is stored as `https://<value>`.

`/api/resumes/files` — nine more operations, the same factory and the same nine handlers as `/api/files`, scoped to `RESUMES`. Unequal parts only:

| Method | Path | Request | Success | Non-happy |
|---|---|---|---|---|
| `GET` | `""` | Query `path` | `200 [FileNode]` | `403 ACCESS_DENIED`, `404 FILE_NOT_FOUND` |
| `POST` | `/upload` | Query `path`; part `file` | `201 FileRecord` | `413 QUOTA_EXCEEDED`, `400 …` |
| `POST` | `/upload-zip` | Query `path`; part `file` | `201 {files, dirs, total_bytes}` | `413`, `400 …` |
| `GET` | `/download` | Query `path` | stream | `404 FILE_NOT_FOUND` |
| `GET` | `/download-folder` | Query `path` | `200 application/zip` | `404 FILE_NOT_FOUND` |
| `DELETE` | `""` | Query `path` | `204` | `404 FILE_NOT_FOUND` |
| `POST` | `/mkdir` | JSON `{path, name}` | `201 {path, name}` | `422` |
| `PATCH` | `/rename` | JSON `{path, new_name}` | `200 FileRecord` or `204` | `404 FILE_NOT_FOUND` |
| `GET` | `/search` | Query `q` | — | always `501 NOT_IMPLEMENTED` |

Auth role is FAMILY or ADMIN instead of any user; bodies are the [files](#files-—-apifiles-tag-files) shapes.

## generated — `/api/generated`, tag `generated`

Read-only history over `users/{user_id}/generated`, section `GENERATED`. Auth user; any storage role that is not `BLOCKED`.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `POST` | `""` | Store one generation run (called by the image generator) | Multipart form, text parts `prompt`, `negative_prompt?`, `seed`, `steps`, `true_cfg_scale`, `width`, `height`, `duration`, file parts `images` (0–10) and `result` (1) | `201 {id, created_at}` | `400 GENERATED_INVALID` (prompt, numeric field, > 10 references, id not allocatable), `413 QUOTA_EXCEEDED` |
| `GET` | `""` | The caller's runs, newest first; unreadable runs skipped | — | `200 {items: [{id, created_at, prompt}]}` | — |
| `GET` | `{run_id}` | One run's metadata; URLs are on this origin | Path `run_id` | `200 {prompt, negative_prompt, seed, steps, true_cfg_scale, width, height, duration, references, result}` | `404 FILE_NOT_FOUND` (unknown or malformed id), `409 GENERATED_META_INVALID` |
| `GET` | `{run_id}/files/{name}` | Stream `result.png` or a listed `ref-N.png` | Path `run_id`, `name` | `200 image/png`, `Content-Disposition: inline` | `404 FILE_NOT_FOUND` (any other name, or unreadable `meta.yaml`) |
| `DELETE` | `{run_id}` | Delete the run's objects, rows and quota | Path `run_id` | `204` | `404 FILE_NOT_FOUND` |

## indexing — no prefix, tag `indexing`

Five routes whose full paths are baked into the decorators. `GET /api/photos/search` is also a `/api/photos` path but belongs to this group.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `/api/photos/search` | Describe-a-photo search over the caller's indexed photos | Query `q` (required), `limit` 1–50 (default 20); optional header `X-Request-Id` (UUID, propagated to RAG) | `200 {items: [{id, file_name, preview_url, original_url, score}], query, total}` | `400 SEARCH_QUERY_INVALID` (empty after trim, > 4000), `503 INDEXING_UNAVAILABLE` (`RAG_ENABLED=false`, or RAG 502/503/504/timeout), `422` (limit out of range) |
| `GET` | `/api/indexing/status` | The caller's link counts | — | `200 {indexed, pending, failed, skipped, total}` | — |
| `GET` | `/api/admin/indexing` | Queue state for an admin, plus a live RAG health probe | — | `200 {by_state, oldest_pending_seconds, last_errors, rag_reachable}` | `403 ACCESS_DENIED` |
| `POST` | `/api/admin/indexing/backfill` | One page of committed records with no link row | Optional JSON `{limit ≥ 1}` | `200 {examined, enqueued, skipped, next_cursor, remaining, status}`; all zeros and `status: "skipped"` when RAG is off | `403 ACCESS_DENIED` |
| `POST` | `/api/admin/indexing/retry` | Re-queue failed links | Optional JSON `{state?: "FAILED"}` | `200 {requeued}` | `403 ACCESS_DENIED`, `422` (any other `state`) |

## admin — `/api/admin`, tag `admin`

Auth role: ADMIN on every route of this group and of the two admin indexing routes above.

| Method | Path | Does | Request | Success | Non-happy |
|---|---|---|---|---|---|
| `GET` | `/users` | Local `users` rows joined with local quota, filtered and paged. `role` on a row is the local projection (`STRANGER`: the table has no role column) | Query `page` ≥ 1, `limit` 1–100, `role?`, `email?` (substring, 1–255) | `200 {items: [UserAdminView], total}` | `403 ACCESS_DENIED` |
| `PATCH` | `/users/{user_id}/role` | Retired: storage roles are assigned in the identity provider | — | `410` | always `410 ACCESS_DENIED` |
| `PATCH` | `/users/{user_id}/quota` | Set total cap (MB) and/or private cap (GB) | JSON `{limit_mb? ≥ 0, private_limit_gb? ≥ 0}`, at least one | `204` | `400 ACCESS_DENIED` (neither given, negative), `404 USER_NOT_FOUND` |
| `POST` | `/users/{user_id}/block` | Set the local `users.is_active` flag to false | — | `204` | `404 USER_NOT_FOUND` |
| `DELETE` | `/users/{user_id}` | Delete the user, their `users/{id}/` prefix and their shared rows | — | `204` | `403 ACCESS_DENIED` (self), `404 USER_NOT_FOUND` |
| `GET` | `/storage` | Bucket capacity and health per disk | — | `200 {disks: [{id, bucket, total_bytes, used_bytes, free_bytes, status}]}` | — |
| `GET` | `/storage/health` | Health per disk | — | `200 {disks: {"<id>": "HEALTHY" \| "LOW_SPACE" \| "UNAVAILABLE"}}` | — |
| `GET` | `/maintenance/run` | **Writes.** Runs pending cleanup, `.tmp` cleanup and quota reconcile now | — | `200 {pending_deleted, tmp_deleted, reconcile: {checked, fixed}}` | — |
| `GET` | `/maintenance/stats` | Counters from the last runs in this process | — | `200 {last_pending_cleanup, pending_deleted, last_tmp_cleanup, tmp_deleted, last_quota_reconcile, quota_checked, quota_fixed}` | — |
| `GET` | `/backup/run` | **Writes.** `pg_dump` into `_meta/backups/` now, then prunes older than 30 days | — | `200 {filename, path, size_bytes}` | `500 INTERNAL_ERROR` (dump failed, `pg_dump` absent) |
| `GET` | `/backup/list` | Backup objects, newest first | — | `200 {items: [{filename, created_at, size_bytes}]}` | — |

`UserAdminView` = `{id, email, role, is_active, created_at, quota_used_bytes, limit_bytes, private_limit_bytes}`.

## service — `main.py`

| Method | Path | Does | Auth | Success |
|---|---|---|---|---|
| `GET` | `/health` | Liveness. No database, bucket or Redis probe. | none; the gateway route is `public` | `200 {"status":"ok"}` |
| `GET` | `/` | SPA `index.html` when `SPA_STATIC_DIR` holds one, else `{"status":"ok","version":"1.0"}` | none | `200` |
| `GET` | `/{full_path:path}` | SPA fallback: a real file under `SPA_STATIC_DIR`, else `index.html` | none | `200` |
