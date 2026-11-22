# task-04 Proxy site block

Story: [US-07](../init.md)

## Outcome

The proxy serves `https://storage.filenkov.store` from the repo's Caddyfile and reloads on the host. The block is present in the repo file already; this task confirms it does the job and records how the host picks it up.

## Paths

- `deploy/auth-gateway/Caddyfile`
- `/etc/caddy/Caddyfile` — a symlink to the repo file

## Done when

The storage name is in the shared host group that proxies to `127.0.0.1:8083` and imports `secure` (HSTS only); the `http://` name redirects to `https://`; `caddy validate --config deploy/auth-gateway/Caddyfile` passes; the certificate is issued for the name; the proxy sets no second security header, which is the [ADR-0001](../../../auth-gateway/adrs/1-edge-in-one-process.md) rule.
