# deletion-worker

Consumer of the `doc.delete` queue. Removes Qdrant points and pages, the MinIO object — only when it belongs to RAG — then sets the MongoDB status to `deleted`.

The order for one message is fixed:

1. Parse the body. Bad JSON, a foreign `schema_version` or a wrong `doc.delete` — `nack` without requeue.
2. Status already `deleted` — `ack`, touch no storage.
3. No document — delete the object at the message's `s3_key`, except keys prefixed `users/`, `_meta/` or `shared/`. Points for the `user_id` + `document_id` pair and the `file_pages` rows are removed either way, then `ack`.
4. Fresh `processing` (heartbeat newer than `STALE_PROCESSING_SECONDS`) — `nack` without requeue.
5. Foreign `s3_key` or foreign `user_id` — `nack` without requeue, delete no bytes.
6. If the status is not yet `deleting`, move it conditionally from `uploaded`, `ready`, `error` or stale `processing`. A race loser re-reads the document and picks its branch again.
7. Write `delete_claimed_at` when empty. While the claim is absent, no object and no points are deleted. Three failed writes shift `updated_at` and route the message to the DLQ.
8. Delete the MinIO object when the document's `object_owner` is not `storage` and the key does not start with `users/`, `_meta/` or `shared/`. The field is read from Mongo; missing or empty means `rag`. `doc.delete` never carries the field. A missing key during deletion is success. For `storage` and foreign prefixes `delete_object` is not called.
9. Delete Qdrant points filtered by `user_id` and `document_id` (`file_id`) in `QDRANT_COLLECTION`, then in `QDRANT_IMAGES_COLLECTION`. Zero points is success. A missing images collection is success.
10. Delete this `file_id`'s `file_pages` documents. Zero pages is success.
11. Move `deleting` → `deleted` conditionally, and only then `ack`.

A repeated `doc.delete` after `deleted` is acknowledged and changes no state. A crash after the object delete and before `deleted` leaves `deleting`; the next delivery finishes the storages and sets `deleted`. No separate repair object is needed.

MinIO, Qdrant or `file_pages` failure after short retries, and a final MongoDB write failure after one extra attempt — `nack(requeue=false)`. The status stays `deleting`. The broker redelivers an unacknowledged message only if the process died before `ack`/`nack`.

At start the process declares the `doc_events` topology idempotently and runs the sweeper once: `status=deleting`, `delete_claimed_at=null`, `updated_at` older than `DELETE_REQUEUE_AFTER_SECONDS`. After that the sweeper repeats no less often than `SWEEP_INTERVAL_SECONDS`. Every channel sets `basic_qos(prefetch_count=1)` before `basic_consume`. The channel count is `DELETION_CONCURRENCY`.

## Variables

Required, no default: `MONGODB_URI`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `QDRANT_URL`, `RABBITMQ_URL`. The log names a missing variable, never its value.

| Variable | Default |
|------------|----------------|
| `S3_BUCKET` | `storage` |
| `S3_REGION` | `us-east-1` |
| `QDRANT_COLLECTION` | `documents` |
| `QDRANT_IMAGES_COLLECTION` | `images` |
| `RABBITMQ_EXCHANGE` | `doc_events` |
| `RABBITMQ_DLX` | `doc_events_dlq` |
| `LOG_LEVEL` | `info` |
| `DELETION_CONCURRENCY` | `1` |
| `STALE_PROCESSING_SECONDS` | `900` |
| `SWEEP_INTERVAL_SECONDS` | `60` |
| `DELETE_REQUEUE_AFTER_SECONDS` | `120` |

`MONGODB_URI` includes the database name. Logs are JSON with `service` equal to `deletion-worker`.

## Run and check

Dependencies install through `uv` from `uv.lock`. `requirements.txt` is the same set of third-party packages without the local project.

```bash
cd src/rag/deletion-worker
uv sync --group dev
uv run pytest
uv run ruff check
uv run ruff format --check
uv run python -m deletion_worker
```

Images: `Containerfile` (Podman) and an identical `Dockerfile`. Build from this directory; the process command is `python -m deletion_worker`. No published port.
