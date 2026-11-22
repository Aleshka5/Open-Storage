# task-02 Config validation

Story: [US-01](../init.md)

## Outcome

`config.yaml` loads, routes compile, and the eight startup rules fail the process. The file matches the gateway message contract.

## Paths

- `src/auth-gateway/gateway/config.yaml`
- `src/auth-gateway/gateway/internal/config/`

## Done when

- `go test ./internal/config/` covers host × path × method.
- Each startup rule has a failing fixture: missing `/**`, unreachable route, duplicate, unknown upstream, unknown service, a secret that is not `env:`, overlapping aliases, empty path after `strip_prefix`.
- The audio catch-all policy gap in [init.md](../../../init.md) is closed in the contract and in the file together.
