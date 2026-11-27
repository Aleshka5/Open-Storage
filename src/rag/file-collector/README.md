# File Collector

PDF intake HTTP service. Default port `8081`.

The namespace contracts live in [docs/rag](../../../docs/rag/init.md): the edge split is [rag/init.md](../../../docs/rag/init.md), the consumer-side obligations are [identity v1](../../../docs/auth-gateway/external-contracts/identity-v1.md). The image builds from `Containerfile` via `podman build`; `Dockerfile` repeats the same text. Dependencies install through `uv` and are pinned in `uv.lock`. `requirements.txt` is an export of that lock, not an install path.

## Variables

Required, no default: `MONGODB_URI`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `RABBITMQ_URL`.

| Variable | Default |
|----------|---------|
| `FILE_COLLECTOR_PORT` | `8081` |
| `MAX_UPLOAD_BYTES` | `524288000` (500 MiB) |
| `S3_BUCKET` | `storage` |
| `S3_REGION` | `us-east-1` |
| `RABBITMQ_EXCHANGE` | `doc_events` |
| `RABBITMQ_DLX` | `doc_events_dlq` |
| `STALE_PROCESSING_SECONDS` | `900` |
| `LOG_LEVEL` | `info` |

At start the service creates the bucket, the `files` collection indexes, and the RabbitMQ topology. A restart deletes no data.

## Routes

| Method | Path | Answer |
|--------|------|--------|
| `GET` | `/health` | `{"status":"ok"}` — no dependency check, no `X-Auth-Subject` |
| `POST` | `/api/files` | `202` file card, publishes `doc.process` |
| `GET` | `/api/files` | the caller's own file list without `deleted` |
| `GET` | `/api/files/{file_id}` | card; another user's or `deleted` — `404` |
| `GET` | `/api/files/{file_id}/content` | PDF bytes; another user's, `deleted` and `deleting` — `404` |
| `DELETE` | `/api/files/{file_id}` | `202` and `doc.delete`; fresh `processing` — `409` |

The user comes only from `X-Auth-Subject` (canonical UUID), otherwise `401 unauthenticated`. `X-Auth-Roles` is the space-separated realm-role list: the exact token `svc:rag:blocked` — `403 forbidden`; `svc:rag:family` and `svc:rag:admin` pass. Legacy headers (`X-Auth-User-Id`, `X-Auth-Role`, `X-User-Id`) are not read.

## Locally

```bash
cd src/rag/file-collector
uv sync --all-groups
uv run ruff check
uv run ruff format --check
uv run pytest
```

Tests call FastAPI through stub MongoDB, MinIO and RabbitMQ and need no stand.
