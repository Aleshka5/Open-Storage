# auth-gateway

Identity and edge. The services share `open_network`, `deploy/auth-gateway/.env`, and `deploy/auth-gateway/docker-compose.yaml`.

This page is how the services interact. Contracts for each service are linked, not copied.

## Services

| Service | Role in the block | Does not |
|---|---|---|
| proxy | Terminates TLS, redirects HTTP to HTTPS, sets HSTS. One upstream per host. | Route by application, authorize, set application headers |
| gateway | BFF, route policy, identity injection, reverse proxy, `/admin` | Store users, issue tokens, store sessions, terminate TLS, render UI |
| idp | Users, roles, sessions, tokens. Google is the only login. | Proxy, route, know hosts |
| idp_db | Postgres state for idp | Anything else |
| resume-page | Static showcase and the `/admin` UI. Documented under [frontend/](frontend/). | Hold tokens, authorize, know secrets |

## Request path

```
Browser
  → proxy          TLS, HSTS. One upstream: gateway
  → gateway        Host + path + method → policy
       no token    → 302 to login, or 401 JSON for API
       bad role    → 403 JSON
       allowed     → strip inbound identity headers, inject identity, proxy
  → upstream       product resource, idp, or resume-page
```

Login and logout go through gateway only:

```
/auth/login     → idp authorization endpoint, kc_idp_hint=google
/auth/callback  → code exchange → cookies → return_to
/auth/logout    → revoke refresh at idp → clear cookies
```

## Ports

| Container | Port | Published | Networks |
|---|---|---|---|
| proxy | 80, 443 | host, including WireGuard | `open_network` |
| gateway | 8080 | `127.0.0.1:8080` | `open_network` plus the product networks named by its upstreams |
| idp | 8080 | no | `open_network` |
| idp_db | 5432 | no | `open_network` |
| resume | 80 | no | `open_network` |

Gateway stores nothing. The session cookie holds the Keycloak refresh token. idp remembers users, roles, and sessions.

## Ownership

| Fact | Owner |
|---|---|
| Who the user is, and their roles | idp |
| Who may call whom | gateway |
| TLS and HSTS | proxy |
| What the page shows | resume-page |

Who-may-edit-whom is enforced in gateway. Who-you-are stays in idp.
