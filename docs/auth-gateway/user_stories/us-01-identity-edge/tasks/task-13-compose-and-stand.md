# task-13 Compose and stand

Story: [US-01](../init.md)

## Outcome

Compose runs proxy, gateway, idp, idp_db, and resume. Network `open_network`, plus product networks only for upstreams named in config. Healthchecks, memory limits, volumes `idp_pgdata` and `caddy_data`.

Makefile targets: `up`, `down`, `rebuild`, `doctor`, `verify`.

## Paths

- `deploy/auth-gateway/docker-compose.yaml`
- `deploy/auth-gateway/Makefile`

## Done when

`podman compose down -v && make up` from empty is ready within 90 seconds. `/readyz` is 200. `make verify` passes.
