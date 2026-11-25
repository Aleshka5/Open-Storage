## Status

Accepted

## Decision

Supersedes the data-service half of [ADR 1](1-own-data-on-open-network.md). The system decision is [ADR-0008](../../../adrs/8-common-data-services.md).

This namespace runs `app` only. `app` joins `open_network` (external, alias `app`) and `common_network` (external). Compose sets `DATABASE_URL` to `postgres:5432`, `REDIS_URL` to `redis://redis:6379`, and `S3_ENDPOINT_URL` to `http://minio:9000`. RabbitMQ and Mongo are not called. The container stays `open-storage-app`. The SPA stays in the app image, as ADR 1 decided.

## Rejected

Private Postgres, MinIO, Redis, RabbitMQ and Mongo on `open_network`. Reaching the shared services through published host ports.

## Cost

`deploy/common` is up first. Database `db_storage` is created on the shared Postgres before the app migrates. `POSTGRES_USER` and `POSTGRES_PASSWORD` in this namespace match the common env. `S3_ACCESS_KEY` and `S3_SECRET_KEY` match `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`.

## Risk

The app shares `common_network` with every other consumer of those services. Header trust still requires that the gateway on `open_network` is the only inbound path. The data services are not on that path.
