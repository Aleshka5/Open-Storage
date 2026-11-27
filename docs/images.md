# Published images

Images this repository builds are published, then run from the registry. The decision is [ADR-0010](../adrs/10-published-images.md).

`REGISTRY` in the namespace env file is the registry host. This system's host is `registry.filenkov.store`. `IMAGE_TAG` selects a date tag `YYYY-MM-DD`. When it is unset, the host runs `latest`.

`make release` from `deploy/<namespace>/` builds that namespace's images, pushes the build machine's local date, and moves `latest` to the same image. `make up` pulls that tag and starts the stack. It does not build. The machine that releases and the machine that runs `make up` can differ. Each runs `podman login` or `docker login` against `REGISTRY` once. The login is not a key in the env file.

`make rebuild` builds from source and starts that image. It does not push. The next `make up` pulls the published tag again.

On a machine where the engine is Podman, `make release` builds with `--no-cache`. Buildah's layer cache follows the `COPY` instruction, not the file contents. `BUILD_FLAGS=` keeps the cache. Docker's cache follows the file contents, so a Docker release uses it.

The engine is `podman` when `podman` is on `PATH`, otherwise `docker`. `ENGINE=docker` or `ENGINE=podman` overrides it.

| Namespace | Repository |
|---|---|
| auth-gateway | `auth-gateway/gateway`, `auth-gateway/resume` |
| open-storage | `open-storage/app` |
| rag | `rag/rag-edge`, `rag/file-collector`, `rag/processor`, `rag/deletion-worker`, `rag/chat`, `rag/frontend`, `rag/embedding`, `rag/ocr` |
| audio | `audio/audio-api`, `audio/diarizer`, `audio/asr-worker`, `audio/frontend` |
| demo | `demo/frontend` |

`common` publishes nothing. Postgres, Redis, MinIO, RabbitMQ, Mongo, Keycloak and Qdrant stay on their upstream registries.

## The registry itself

The registry runs from [`deploy/registry-compose.yaml`](../deploy/registry-compose.yaml) — one `registry:latest` container with htpasswd auth, host publish `5000:5000`, data in `~/.registry/data`. It is not a namespace: no env file, no Makefile, no network of its own. `docker compose -f deploy/registry-compose.yaml up -d` starts it.

`https://registry.filenkov.store` is served by the edge proxy with `tls internal` and a LAN / WireGuard gate ([Caddyfile](../deploy/auth-gateway/Caddyfile)). A machine that pushes or pulls must trust Caddy's local CA root, the same condition as `meet.filenkov.store`, and be logged in (`podman login registry.filenkov.store` / `docker login`). The password file is `~/.registry/registry.password` on the host; it is never a repository file.

To run a date that is not `latest`:

```bash
IMAGE_TAG=YYYY-MM-DD make up
```
