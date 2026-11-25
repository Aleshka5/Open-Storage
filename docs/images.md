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

`common` publishes nothing. Postgres, Redis, MinIO, RabbitMQ, Mongo, Keycloak and Qdrant stay on their upstream registries.

To run a date that is not `latest`:

```bash
IMAGE_TAG=YYYY-MM-DD make up
```
