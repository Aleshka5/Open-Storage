# task-05 Volumes

Story: [US-05](../init.md)

## Outcome

Postgres, redis and minio keep their state in named volumes; the blob data is a named volume whose host path is the one [US-08](../../us-08-data-cutover/init.md) copies into.

## Paths

- `deploy/open-storage/docker-compose.yaml`

## Done when

`podman volume ls` shows the namespace's volumes with the `open-storage-` prefix; `make down` keeps them; the minio volume's host path is recorded in `deploy/open-storage/.env.example` as a variable, not hardcoded in the compose; a restart of each data service keeps its rows and objects.
