# proxy — message contract

Caddy 2.11. One file, `Caddyfile`: ([Caddyfile](../../../../deploy/auth-gateway/Caddyfile)). Ports 80 and 443. Bind is the LAN address plus the WireGuard address.

Three jobs: terminate TLS, redirect `http://` to `https://`, set HSTS. One upstream per host: `gateway:8080`.

Proxy does not set `Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, or `Referrer-Policy`. Those depend on the host and belong to gateway. A duplicate header is a defect: browsers intersect the policies.

## Host classes

| Class | Hosts | Certificate |
|---|---|---|
| Public | `filenkov.store`, `storage.`, `image.`, `rag.`, `audio.`, `llm.`, `observer.`, `id.` | ACME HTTP-01. One A record per name. No wildcard. |
| LAN / WireGuard | `meet.filenkov.store` | `tls internal`. Clients must install the local CA root. Say so wherever this host is documented. |
| Outside SSO | `hermes.filenkov.store` → `127.0.0.1:9119`, `lite-llm.filenkov.store` → `127.0.0.1:4000` | Public ACME. Gateway does not authenticate them. `hermes` also keeps a LAN / WireGuard `remote_ip` gate ([ADR-0005](../adrs/0005-port-from-auth-service.md)). |

Protocols: `h1 h2`. No HTTP/3.

The HTTP redirect lists every site name. With `default_bind` set, Caddy does not create that redirect itself.
