# task-02 Own data services

Story: [US-05](../init.md)

## Outcome

`deploy/open-storage/docker-compose.yaml` starts app, postgres, minio and redis, each with an explicit container name, and names no external network.

## Paths

- `deploy/open-storage/docker-compose.yaml`

## Done when

`podman-compose config` resolves the file with no `external: true` left, every `container_name` starts `open-storage-`, and `make up` from empty volumes reaches `/health` 200. The legacy compose's `common_network`, `user_network`, `auth_network` and `rag_edge` entries are gone.
