# common

Postgres, Redis, MinIO, RabbitMQ and Mongo on `common_network`, for any compose that joins that network. How they connect is [init.md](init.md). The decision is [ADR-0008](../../adrs/8-common-data-services.md).

Copy [deploy/common/.env.example](../../deploy/common/.env.example) to `.env` beside it and set the four secrets. From `deploy/common/` run `make doctor`, then `make up`. `make down` leaves the named volumes and the MinIO directory in place.

Do not run this file and Common `docker-compose-common.yml` together: both use the container names `postgres`, `redis`, `minio`, `rabbitmq` and `mongo`, and both claim the network `common_network`.

MinIO refuses to start when `/media/aleksey/HardDisk/minio` has no `.minio.sys/format.json`. The disk must be mounted before `make up`.
