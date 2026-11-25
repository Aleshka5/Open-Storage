# ADR-0008 Common data services

## Status

Accepted

## Decision

Postgres, Redis, MinIO, RabbitMQ and Mongo run in the `common` namespace, on the network `common_network`. Service names, container names, images, the MinIO host path, volume keys and env keys match Common `docker-compose-common.yml` and `.env.common`. The compose file is [docker-compose.yaml](../deploy/common/docker-compose.yaml). Another namespace reaches a service by its name on `common_network`. `open-storage` does not define these services.

## Rejected

A second copy of the same services inside `open-storage` on `open_network`. Host-published ports as the way a product connects. A different network name or prefixed container names.

## Cost

`common` is up before a product that uses it. One MinIO directory (`/media/aleksey/HardDisk/minio`) and one set of named volumes serve every product. A product database is a database in this Postgres, not another server.

## Risk

Any container on `common_network` can open these ports. The gateway stays on `open_network` and does not join `common_network`.
