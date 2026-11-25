## Status

Superseded in part by [ADR 3](3-app-on-common-data.md). The SPA image and the `app` name on `open_network` still hold. This namespace no longer runs Postgres, MinIO or Redis.

## Decision

This namespace runs its own Postgres, MinIO and Redis, joins the `open_network` the auth-gateway namespace already creates (`external: true`), names every container `open-storage-*`, and builds the SPA into the app image. The compose file is [docker-compose.yaml](../../../deploy/open-storage/docker-compose.yaml). The image build is [app/Dockerfile](../../../deploy/open-storage/app/Dockerfile). The service name on that network stays `app`, which is the storage upstream in [gateway config](../../../src/auth-gateway/gateway/config.yaml).

## Rejected

Borrowing Postgres, MinIO and Redis from `common_network`. A second bridge the gateway cannot reach. Bare container names. An nginx sidecar or a Vite dev container for the SPA.

## Cost

`open_network` has to exist before `make up`. Blob bytes sit on the host path `MINIO_DATA_PATH`. Postgres and Redis use named volumes. The app publishes no host port.

## Risk

Postgres, MinIO and Redis share `open_network` with the gateway, so any container on that network can route to them. The gateway is the only published entry.
