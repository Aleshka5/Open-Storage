# auth-gateway

Not a development spec. Contracts are under this directory's service folders. This page is what the namespace is and how to run it.

## Purpose

One login for the `filenkov.store` hosts. TLS at the edge, identity in Keycloak, authorization in the gateway. Product applications stay outside this namespace and receive the [identity v1](external-contracts/identity-v1.md) headers.

## Stack

| Piece | Stack |
|---|---|
| proxy | Caddy 2.11, run by systemd on the host |
| gateway | Go 1.26. stdlib, `gopkg.in/yaml.v3`, `github.com/coreos/go-oidc/v3`, `github.com/go-jose/go-jose/v4`. Budget: 4200 lines of Go, tests excluded ([ADR-0007](adrs/7-gateway-line-budget.md)). |
| idp | Keycloak 26.8.2, realm imported from `realm.json` |
| idp_db | Postgres 17 |
| resume-page | Vite 7, React 19, TypeScript, nginx |
| Run | podman-compose 5.7 |

There is no Redis, no user-catalog service, and no second identity store.

## Run

From `deploy/auth-gateway/`. The proxy is the host's Caddy; `deploy/auth-gateway/Caddyfile` is the source and `/etc/caddy/Caddyfile` is a symlink to it.

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

`make doctor` checks compose, the env file, the Caddyfile, and that the gateway builds. `make verify` runs `scripts/golden.sh`: one request per SSO host through the proxy and directly against the gateway, both probes, and the Caddyfile.

A config change is a restart of gateway, not a reload. A proxy change is `caddy validate` then reload. Restarting gateway does not sign people out.

## Backup

| Data | Where |
|---|---|
| Gateway config, Caddyfile, realm.json | git |
| Users, sessions, signing keys | `idp_db` (`pg_dump` daily, onto disk, not into a container volume) |
| `GATEWAY_SESSION_KEY` | env file outside git. Losing it signs everyone out. It does not lose data. |
| ACME certificates | reissued automatically. Keep the internal CA root if clients already trust it. |
