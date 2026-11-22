# app — external contract

What the app requires from systems outside itself. One row per call. "Contract" is what the other side must keep true for this app to work; the linked document owns the fact.

The app trusts identity because it has one inbound path, the gateway on `open_network`. It sets no response header the gateway already sets.

## auth-gateway

| External system | Call | Used for | Contract it must satisfy |
|---|---|---|---|
| gateway | Inbound: any request to `storage.filenkov.store`, proxied to `app:8000` | Every request the product serves | Header set, strip list and header-trust condition: [identity v1](../../auth-gateway/external-contracts/identity-v1.md). Host, upstream, policy and timeout: [upstreams](../../auth-gateway/external-contracts/upstreams.md), [gateway config](../../../src/auth-gateway/gateway/config.yaml) |
| gateway → app | `X-Auth-Subject` | The user key. Every `users.id`, every `users/{id}/…` object prefix, every quota row, every `file_records.user_id`. The reader does not parse it; the column is still UUID, so a non-UUID subject is not inserted | Stable per person, one value per person, present on every non-public route |
| gateway → app | `X-Auth-Email`, `X-Auth-Name` | `users.email` (unique), display | Email is the identity the local projection refuses to duplicate |
| gateway → app | `X-Auth-Roles` | Projected onto `STRANGER` / `FAMILY` / `ADMIN` / `BLOCKED`; `BLOCKED` wins, then `ADMIN`, then `FAMILY` | Realm roles only, as defined in [idp roles](../../auth-gateway/idp/init.md): `admin`, `svc:storage:{admin,family,blocked}` |
| gateway → app | `X-Auth-Session` | Read with the other v1 headers. Not the vault Redis key | One `sid` per login |
| gateway → app | Injected `Authorization: Bearer …` | Not read by the app | — |
| gateway → app | Session cookie `__Secure-open_session`, `Domain=.filenkov.store`, HttpOnly | The vault hashes it in-process; the Redis key is `private_key:` plus that SHA-256 hex. A missing cookie is 401. Two cookies are two keys | Present on this origin; its value different per login; not rotated mid-session |
| app → gateway | none | The app makes no call to the gateway | — |
| gateway → client | `{"error":"<code>"}` on its own refusals | Caller sees edge errors for `401`/`403`/`404`/`429`/`502`/`504` before the app is reached | [identity v1 errors](../../auth-gateway/external-contracts/identity-v1.md), [gateway API contract](../../auth-gateway/gateway/api-contract.md) |

The app's own identity failures answer in its own envelope (`401 {"detail":{"error_code":"UNAUTHORIZED",…}}`), so one browser on one origin sees two error shapes. Recorded, not resolved, in the [namespace findings](../init.md#mismatches-with-the-legacy-project).

## postgres

| Call | Used for | Contract |
|---|---|---|
| `asyncpg` over `DATABASE_URL`, database `db_storage`, role `storage` | All metadata: `users`, `file_records`, `user_quota_usage`, `file_index_links` | PostgreSQL with the native enums `file_section`, `file_status`; `timestamp with time zone`; `alembic upgrade head` runs at container start and must succeed or the container stops |
| `pg_dump` (external binary, installed in the image with `postgresql-client`) | `GET /api/admin/backup/run` | `pg_dump` accepts the DSN after `+asyncpg` is stripped, and its version is at least the server's |

Schema and ownership: [app/init.md](init.md#database).

## minio (S3 API)

| Call | Used for | Contract |
|---|---|---|
| `HEAD` bucket, `ListObjectsV2` on the whole bucket, paginated | Capacity and health: used bytes are summed over every object in the bucket | The credentials may list the entire bucket |
| `GET <endpoint>/minio/admin/v3/info`, SigV4-signed | Total capacity of the drives | MinIO Admin API, not plain S3; when it fails the app assumes a 1 TiB total |
| `PutObject`, `CreateMultipartUpload`/`UploadPart`/`CompleteMultipartUpload`, `CopyObject`, `UploadPartCopy`, `DeleteObject(s)`, `HeadObject`, `GetObject` (`Range` unused) | Every read and write of every section | Path-style addressing (`S3_PATH_STYLE=true`), one bucket, no object lock, no versioning dependency; a part size of 8 MiB; `CopyObject` up to 5 GiB, multipart copy above |
| Bucket `storage` shared with RAG | RAG reads the keys the app owns | The app is the only writer and the only deleter; RAG never writes or deletes an object |

Key layout: [app/init.md](init.md#storage-layout-in-minio). The RAG side of the sharing is in [rag-edge](#rag-edge).

## redis

| Key | Used for | Contract | TTL |
|---|---|---|---|
| `private_key:<sha256>` | The base64 AES key that unlocks the vault for one session. `<sha256>` is the hex digest of the `__Secure-open_session` cookie, not the raw cookie | Plain `SET`/`GET`/`DEL`/`TTL`; no cluster-side TTL loss | `PRIVATE_SESSION_TTL_HOURS` (4 h), set on unlock, never extended |
| `unlock_attempts:<user_id>:<ip>` | Unlock and reset rate limit (5 per 900 s) | `INCR` + `EXPIRE` on first hit | 900 s |
| `auth_rate:<path>:<ip>` | Rate limit on `/api/auth/login` and `/api/auth/register` | Same | 60 s |
| `oauth_state:<state>`, `oauth_ticket:<ticket>` | Written and consumed by routes that answer `410` | — | 600 s / 120 s |

`REDIS_URL`, default `redis://redis:6379`. Redis is not a cache and not a session store for identity: the only durable thing in it is the vault key, and its loss locks every vault (the data stays).

The app makes no identity HTTP call. Role and subject come from the headers in [identity v1](../../auth-gateway/external-contracts/identity-v1.md). The admin user list is the local `users` table.

## rag-edge

| Call | Used for | Contract |
|---|---|---|
| `GET /health` | `rag_reachable` in `GET /api/admin/indexing` | `200 {"status":"ok"}`; anything else is "not reachable" |
| `POST /api/files/documents` | Register a PDF, DOCX or XLSX | `202` + `{file_id, status, …}`; `409 duplicate_file` with `error.details.file_id` |
| `POST /api/files/images` | Register a JPEG, PNG, WebP or GIF, or a photo's JPEG preview | Same |
| `GET /api/files/{rag_file_id}` | Poll a registration | `200` + `status` in `uploaded`/`processing`/`ready`/`error`/`deleting`/`deleted` |
| `PUT /api/files/{rag_file_id}/object` | Re-key after a rename or move | `202`; `409 content_changed` when the bytes moved too |
| `DELETE /api/files/{rag_file_id}` | Remove vectors for a deleted record | `202`; `404` and `409 file_busy` count as "vectors gone" |
| `GET /api/chats/image-search?q=&limit=&offset=` | `GET /api/photos/search` | `200 {items: [{file_id, file_name, score}], limit, offset, next_offset?}` |

Identity on every call: `X-Auth-User-Id` (the file owner) and `X-Request-Id`. No cookie, no `Authorization`, no role header: RAG resolves the caller from the header and must keep doing so.

The manifest the app sends is `{s3_key, file_name, content_sha256, file_size, content_type, origin: "storage"}`, where `s3_key` is the object key RAG reads from the shared `storage` bucket. Timeout `RAG_TIMEOUT_SECONDS` (10). Transport failures, `502`/`503`/`504` and timeouts are outages; `RAG_ENABLED=false` disables the job, the startup pass and search with no outbound call.

## Network reach

| Call | Network |
|---|---|
| gateway → app | `open_network` |
| app → postgres, minio, redis | the namespace's own bridge |
| app → rag-edge | `rag_edge` |

See the [namespace page](../init.md#networks) for why each exists.
