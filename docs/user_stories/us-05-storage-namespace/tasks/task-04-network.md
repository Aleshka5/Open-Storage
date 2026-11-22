# task-04 Network

Story: [US-05](../init.md)

## Outcome

The app is reachable by the gateway on `open_network` and by nothing else. The gateway reaches `app:8000`, which is the `storage` upstream already declared in `src/auth-gateway/gateway/config.yaml`.

## Paths

- `deploy/open-storage/docker-compose.yaml`

## Done when

`open_network` is declared `external: true` and exists after the auth-gateway namespace is up; the app joins it and no other network; `podman exec` from a gateway container resolves `app` to the storage app container; no port is published on `0.0.0.0` for the app.
