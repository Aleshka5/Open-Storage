# task-01 Repository skeleton

Story: [US-01](../init.md)

## Outcome

Gateway builds. Compose config is valid. `.env` is gitignored and `.env.example` is not.

## Paths

- `src/auth-gateway/gateway/go.mod`
- `src/auth-gateway/gateway/cmd/gateway/main.go`
- `deploy/auth-gateway/docker-compose.yaml`
- `deploy/auth-gateway/.env.example`
- `deploy/auth-gateway/Makefile`

## Done when

- `go build ./...` passes on an empty `main`.
- `podman compose -f deploy/auth-gateway/docker-compose.yaml config` is valid.
- `.env` is ignored. `.env.example` is tracked.
