> **ID:** US-05
> **Status:** TODO
> **Specs:** [repository layout](../../repository-layout.md), [docs/init.md](../../init.md), [identity v1](../../auth-gateway/external-contracts/identity-v1.md)

## Overview

The storage product becomes a namespace of this repository: one network, one env file, one compose file, its own Postgres, MinIO and Redis. Today it is a separate repository whose compose borrows `common_network` for postgres, minio and redis and joins three other projects' networks to reach them. This story moves it in and takes back what it owns. Identity is not touched here — that is [US-06](../us-06-identity-v1/init.md); routing is [US-07](../us-07-edge-host/init.md); the data is [US-08](../us-08-data-cutover/init.md).

Mismatch: D2 and the acceptance lines that name `open-storage-postgres`, `open-storage-minio` and `open-storage-redis` are not the running layout. [US-15](../us-15-common-network/init.md) and [ADR 3](../../open-storage/adrs/3-app-on-common-data.md) put those services in the `common` namespace.

Tasks: [repository layout](tasks/task-01-layout.md), [own data services](tasks/task-02-compose-data.md), [env and Makefile](tasks/task-03-env-makefile.md), [network](tasks/task-04-network.md), [volumes](tasks/task-05-volumes.md), [SPA in the image](tasks/task-06-spa-image.md), [suite from the new location](tasks/task-07-suite.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The code lives at `src/open-storage/{app,spa}` and the deployment at `deploy/open-storage/`, per [repository-layout.md](../../repository-layout.md). The legacy repository is not a submodule and not a nested git repo. | Keeping the legacy repository and pointing compose at a sibling checkout |
| D2 | The namespace runs its own `postgres`, `minio` and `redis`. It leaves `common_network` entirely. | Keeping `common_network` as an external network and its services as external |
| D3 | Containers are named `open-storage-<service>` (e.g. `open-storage-app`, `open-storage-postgres`). No container name is a bare product word. | Relying on compose project prefixes, which change with the directory name |
| D4 | `open_network` is the one network. The auth-gateway namespace already owns it; this namespace joins it as `external: true`. The app does not join a per-namespace internal network for the edge hop. | A second bridge network only this namespace uses, which the gateway cannot reach |
| D5 | The SPA is built in the app image as a multi-stage build and served from `SPA_STATIC_DIR`. No sidecar nginx, no Vite dev container in production. | Serving the SPA from a separate upstream, which gives the host two upstreams for one origin |
| D6 | Named volumes for the three data services. Nothing binds a host directory except the blob data, which is a documented host path so the cutover in [US-08](../us-08-data-cutover/init.md) can copy into it. | Binding every volume to a host path, which makes ownership and permissions host-dependent |

## Goals

- `make up` in `deploy/open-storage/` starts app, postgres, minio, redis from empty volumes.
- The app reaches its database, bucket and cache by service name on `open_network`.
- The app image contains the built SPA.

## Non-goals

- Changing what the app returns or who it trusts. That is US-06.
- The gateway host block and the proxy site block. That is US-07.
- Copying data. That is US-08.
- RAG indexing. `RAG_ENABLED=false` stays the default in the env file until [US-08](../us-08-data-cutover/init.md) re-queues the links.

## User Story

**As** the operator, I want the storage product to be one namespace in this repository, so that one `make up` brings it up with its own data services and no other project has to stay alive for it to work.

**Acceptance**

- `git ls-files src/open-storage deploy/open-storage` lists the app, the SPA and the four deploy files, and `git ls-files | grep -c '^src/WebStorage/'` is `0`.
- `cd deploy/open-storage && make up` followed by `curl -fsS localhost:<app-port>/health` answers 200 with volumes empty.
- `podman ps --format '{{.Names}}'` shows `open-storage-app`, `open-storage-postgres`, `open-storage-minio`, `open-storage-redis` and no name without the prefix.
- `podman inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' open-storage-app` prints `open_network` only.
- `podman exec open-storage-app printenv | grep -E 'DATABASE_URL|REDIS_URL|S3_ENDPOINT_URL'` prints hosts `open-storage-postgres`, `open-storage-redis`, `open-storage-minio`.
- `podman exec open-storage-app test -f /opt/spa/index.html` succeeds, and `curl -fsS localhost:<app-port>/` returns the SPA's `index.html`. The container port stays `8000`, which the `storage` upstream in `config.yaml` names.
- `cd src/open-storage/app && pytest` collects the same test files as the legacy `backend/tests` and passes.

## Definition of Done

- [ ] The four files exist under `deploy/open-storage/` and pass `podman-compose config`.
- [ ] No service in the compose names an external network.
- [ ] `.env.example` carries no literal secret.
- [ ] The acceptance items above hold on the host.
- [ ] `docs/open-storage/` links this story's names and does not restate them.
