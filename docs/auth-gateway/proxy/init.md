## Files

| Path | What |
|---|---|
| [Caddyfile](../../../deploy/auth-gateway/Caddyfile) | Site config, in git. The live edge reads it via the `/etc/caddy/Caddyfile` symlink. Every SSO host and `id.` are on `127.0.0.1:8083`. `id.` is public ([ADR-0013](../adrs/13-idp-host-public.md)). |
| [Caddyfile symlink](/etc/caddy/Caddyfile) | Symlink to that file |
| [Service](/var/lib/caddy/.local/share/caddy/) | ACME certs and the local CA. Not backed up. Reissued, except the CA root clients already trust. |

## Certificates

| Class | Issue | Renew |
|---|---|---|
| ACME | First request | Automatic, 30 days before expiry |
| `tls internal` | Caddy local CA | Automatic, 12 months |

ACME fails when port 80 is closed, the A record is missing, or a CAA record blocks the issuer.

Restart instead of Reload because of `admin off`

## When it fails

Check in this order:

| Symptom | Layer | Check |
|---|---|---|
| `SSL alert internal error`, `curl: (35)` | proxy | Site block or certificate missing |
| `404 {"error":"not_found"}` | gateway | Host header against `127.0.0.1:8080` |
| `502` | upstream | Fetch the upstream from the gateway container |
| `403` from Caddy on `meet` | proxy | Source is outside LAN / WireGuard |

Caddy does not buffer bodies. A 30-minute upload and an SSE chat pass through. Grace period 10 seconds.
