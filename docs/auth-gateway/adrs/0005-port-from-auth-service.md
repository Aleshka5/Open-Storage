# ADR-0005 Port the edge from Auth-Service

## Status

Accepted

## Decision

The `auth-gateway` namespace starts as a port of the running stack in `~/projects/Auth-Service`, not as a rewrite.

Carried: route matching, `config.yaml` validation, the reverse proxy (WebSocket upgrade, unbuffered SSE, per-host response-header timeouts), refresh single-flight, `return_to`, the access log, the security headers, and the SPA with its tree and registry invariants.

Dropped with the port, because the contracts replace them: own HS256 tokens (`internal/token`), the Google exchanger, the User-Service client and its per-service role lookups, the Redis session id, the rejected cache, and the separate `api` process.

Also decided in this change, because they were open:

| # | Decision | Rejected | Cost |
|---|---|---|---|
| 1 | One error envelope, string form: `{"error":"<snake_case>"}` everywhere, including `/admin` (`{"error":"last_admin"}`, 409) | The object form `{"error":{"code","message"}}` | `/admin` error text moves from code+message to a single code; the identity v1 table stays as five external consumers already read it |
| 2 | `audio.filenkov.store` catch-all policy is `session` | `service(audio, family, admin)` on the UI too | The SPA shell is visible to any signed-in account; `/api/**` still needs `svc:audio:family` |
| 3 | `hermes.filenkov.store` leaves SSO (proxy contract) **but keeps a LAN / WireGuard gate** in Caddy | No gate, as the contract's site shape shows | A deviation from the proxy contract, recorded here and in that contract. The dashboard keeps its own login; nothing else about it changes |
| 4 | The proxy runs as the host's systemd Caddy, not as a compose service | A proxy container | The compose file covers gateway, idp, idp_db and resume. The proxy contract already puts the file at `/etc/caddy/Caddyfile` and the certificates in `/var/lib/caddy`, and two upstreams are host loopback ports (`127.0.0.1:9119`, `127.0.0.1:4000`) that a container cannot reach |

## Cost

Carried code is 1,334 non-test lines; the new packages add about 1,000. The 2,000-line cap in the namespace README has roughly five lines of margin, so the cap is a check in every gateway task, not a final one.

## Because

The routing and proxy layer is the part that is expensive to get right and cheap to keep: 101 upgrades, SSE that is not buffered, per-host timeouts and a hijack-safe status wrapper already have tests. The contracts change identity, not plumbing. A rewrite would re-earn those bugs and would not remove a single line of the SPA.
