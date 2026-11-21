# proxy — external contract

## Files

| Path | What |
|---|---|
| `deploy/auth-gateway/Caddyfile` | Site config, in git. The live edge reads it via the `/etc/caddy/Caddyfile` symlink; `make mvp-config` generates `Caddyfile.mvp` from it for the MVP stand |
| `/etc/caddy/Caddyfile` | Symlink to that file |
| `/var/lib/caddy/.local/share/caddy/` | ACME certs and the local CA. Not backed up. Reissued, except the CA root clients already trust. |

## Neighbors

The only SSO upstream is `gateway:8080` on `open_network`. Product ports are not opened here.

`meet` accepts `remote_ip` `10.10.0.0/24`, `192.168.1.0/24`, and `127.0.0.1`. Anyone else gets `403` from Caddy, before gateway.

## Certificates

| Class | Issue | Renew |
|---|---|---|
| ACME | First request | Automatic, 30 days before expiry |
| `tls internal` | Caddy local CA | Automatic, 12 months |

ACME fails when port 80 is closed, the A record is missing, or a CAA record blocks the issuer.

Replacing the Caddy volume changes the local CA. Clients must install the new root. The failure looks like a certificate error, not a 404.

Reload applies site changes without dropping connections. A full restart is only for `default_bind` or global server options, and it drops TLS for every product.

## When it fails

Check in this order:

| Symptom | Layer | Check |
|---|---|---|
| `SSL alert internal error`, `curl: (35)` | proxy | Site block or certificate missing |
| `404 {"error":"not_found"}` | gateway | Host header against `127.0.0.1:8080` |
| `502` | upstream | Fetch the upstream from the gateway container |
| `403` from Caddy on `meet` | proxy | Source is outside LAN / WireGuard |

Caddy does not buffer bodies. A 30-minute upload and an SSE chat pass through. Grace period 10 seconds.
