> **ID:** US-15
> **Status:** DONE
> **Specs:** [ADR-0008](../../../adrs/8-common-data-services.md), [common](../../common/init.md), [open-storage ADR 3](../../open-storage/adrs/3-app-on-common-data.md)

## Overview

Postgres, Redis, MinIO, RabbitMQ and Mongo leave the open-storage compose and run as the `common` namespace on `common_network`, with the names and env keys from Common.

## Locked decisions

| # | Decision |
|---|---|
| D1 | New namespace `common`: one network `common_network`, one env file, one compose file. |
| D2 | Service names, container names, images, MinIO path and env keys match Common. |
| D3 | `open-storage` compose keeps `app` only. The app joins `common_network` and uses `postgres`, `redis`, `minio`. |

## Goals

- Other products can join `common_network` and use the same services.
- The open-storage app reaches them by those DNS names.

## Non-goals

- Moving auth-gateway's `idp_db`.
- Creating database `db_storage` or bucket `storage` from the common compose.
- A data migration from the old `open-storage-*` volumes.

## User Story

**As** an operator of another product, I want the shared data services on `common_network`, so that I can use them without starting a second copy inside open-storage.

**Acceptance**

- `deploy/common/docker-compose.yaml` defines `postgres`, `redis`, `minio`, `rabbitmq`, `mongo` on `common_network`.
- `deploy/open-storage/docker-compose.yaml` does not define those services.
- The app's `DATABASE_URL`, `REDIS_URL` and `S3_ENDPOINT_URL` use `postgres`, `redis` and `minio`.

## Definition of Done

- [x] ADR-0008 and the common namespace docs exist before the compose file.
- [x] Open-storage docs, env example and the layout test match the compose file.
- [x] `docker compose config` succeeds for both compose files.
