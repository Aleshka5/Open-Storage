# auth-gateway

Not a development spec. Contracts are under this directory's service folders. This page is what the namespace is and how to run it.

## Purpose

One login for the `filenkov.store` hosts. TLS at the edge, identity in Keycloak, authorization in the gateway. Product applications stay outside this namespace and receive the [identity v1](external-contracts/identity-v1.md) headers.

## Stack

| Piece | Stack |
|---|---|
| proxy | Caddy 2.11 |
| gateway | Go 1.26. stdlib, `gopkg.in/yaml.v3`, `github.com/coreos/go-oidc/v3`. Budget: 2000 lines of Go, tests excluded. |
| idp | Keycloak 26.8.2, realm imported from `realm.json` |
| idp_db | Postgres 17 |
| resume-page | Vite 7, React 19, TypeScript, nginx |
| Run | podman-compose 5.7 |

There is no Redis, no user-catalog service, and no second identity store.

## Run

From `deploy/auth-gateway/`. Code is not in the tree yet, so `up` has no services until that changes.

```bash
cp ../../.env.example .env
cat .env.example >> .env
# fill the secret values in .env
make doctor
make up
make verify
make down
```

`.env` is not committed. Names are in [.env.example](../../deploy/auth-gateway/.env.example). Shared names are in the repository `.env.example`.

`make doctor` checks compose, the env example, and that the gateway is ready. `make verify` checks each SSO host through the proxy and directly against the gateway.

A config change is a restart of gateway, not a reload. A proxy change is `caddy validate` then reload. Restarting gateway does not sign people out.

## Backup

| Data | Where |
|---|---|
| Gateway config, Caddyfile, realm.json | git |
| Users, sessions, signing keys | `idp_db` (`pg_dump` daily, onto disk, not into a container volume) |
| `GATEWAY_SESSION_KEY` | env file outside git. Losing it signs everyone out. It does not lose data. |
| ACME certificates | reissued automatically. Keep the internal CA root if clients already trust it. |
