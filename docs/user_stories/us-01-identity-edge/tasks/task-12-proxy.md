# task-12 Proxy

Story: [US-01](../init.md)

## Outcome

`Caddyfile` matches the proxy message contract. Nine SSO sites proxy to `gateway:8080`. `meet` uses `tls internal` and `remote_ip`. `hermes` and `lite-llm` go to local ports. HTTP redirects to HTTPS. Protocols are `h1 h2`.

## Paths

- `deploy/auth-gateway/Caddyfile`

## Done when

`caddy validate` passes. `curl -I https://<host>` shows HSTS. `http://` returns `308` to `https://`.
