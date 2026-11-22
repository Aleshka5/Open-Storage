# task-01 Upstream and host block

Story: [US-07](../init.md)

## Outcome

The `storage` upstream and the `storage.filenkov.store` host block resolve to the namespace's app container and start the gateway without a config error.

## Paths

- `src/auth-gateway/gateway/config.yaml` — read, not edited
- `deploy/open-storage/docker-compose.yaml` — the `app` service name

## Done when

`upstreams.storage` is `app:8000`; the app container answers on `app:8000` from the gateway container; the gateway starts with the block present; `policy.Parse` accepts `service(storage, family, admin)` because `storage` is in `services:`; a mismatch found between the block and the app (port, path, container name) is written down as a finding.
