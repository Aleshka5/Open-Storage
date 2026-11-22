# gateway — API contract

What the gateway serves, to whom, with which headers and bodies. Identity headers handed to product apps are owned by [identity v1](../external-contracts/identity-v1.md); this file owns every endpoint the gateway itself answers, plus the ones it proxies for a known upstream. Configuration is in [init](init.md). Outbound calls are in [external-contracts.md](external-contracts.md).

Listen `:8080`, path matching first-wins per host, exactly one `/**` per host and it is last. Every response carries the security headers of its host.

## Endpoint inventory

| Method | Path | Host | Caller | Policy | Answered by |
|---|---|---|---|---|---|
| `GET` | `/healthz` | any | operator, `golden.sh` | none | gateway |
| `GET` | `/readyz` | any | operator, `golden.sh` | none | gateway |
| `GET` | `/metrics` | any | Prometheus | none | `404` here; the second listener serves it |
| `GET` | `/auth/login` | apex | browser | none | gateway BFF |
| `GET` | `/auth/callback` | apex | idp | none | gateway BFF |
| `GET` | `/auth/session` | apex | SPA | none (anonymous answers `401`) | gateway BFF |
| `POST` | `/auth/logout` | apex | SPA | same-origin header required | gateway BFF |
| `GET` | `/admin/users` | apex | `/admin` UI | `admin` | gateway |
| `PUT` | `/admin/users/{id}/roles/{svc}` | apex | `/admin` UI | `admin` or `svc:{svc}:admin` | gateway |
| `PATCH` | `/admin/users/{id}` | apex | `/admin` UI | `admin` | gateway |
| `PUT` | `/admin/users/{id}/admin` | apex | `/admin` UI | `admin` | gateway |
| `POST` | `/api/chat` | apex | resume page | `public` | gateway chat handler, SSE |
| `GET` | `/api/services` | apex | resume page | `session` | proxied to `switch`, token injected |
| `GET`+ | `/api/services/**` | apex | resume page | `admin` | proxied to `switch`, token injected |
| any | everything else | any host | — | per host | proxied to the host upstream |

Anything under `/users/**` on the apex is `policy: deny`. The implementation answers a `deny` route before it looks at the caller, so a `deny` path is always `404 not_found` and never a login redirect; that is also why `/users*` appears in the `401` list above — the path shape decides the answer only when the policy is not `deny`.

## Common rules

**Policies.** `public` (anonymous included), `session` (an enabled account), `admin` (realm role `admin`), `service(<svc>)` (`svc:<svc>:family` or `:admin`), `service(<svc>, admin)`, `deny` (`404`). `svc:<svc>:blocked` beats `session` on a host whose `service:` is set and answers `403 blocked`.

**Anonymous, by request shape.** Browser navigation: `302` to `/auth/login?return_to=<url>`. Non-navigation — `/api/*`, `/users*`, and anything with `Upgrade: websocket` — gets `401` JSON. A missing or `deny`ed route: `404` JSON, always.

**Error envelope.** One string form everywhere, `/admin` included: `{"error":"<snake_case>"}`.

| Value | HTTP | When |
|---|---|---|
| `unauthorized` | 401 | No session, or the session expired and the refresh failed |
| `forbidden` | 403 | Signed in, role does not allow |
| `blocked` | 403 | `svc:<svc>:blocked` and the host names `service: <svc>` |
| `not_found` | 404 | Unknown route or unknown user id |
| `validation` | 400 | Bad body, or `svc=admin` on the service-role path |
| `last_admin` | 409 | The change would leave no realm `admin` |
| `idp_unavailable` | 503 | The Admin API did not answer |
| `auth_unavailable` | 503 | `/readyz` when discovery or JWKS never loaded; `GET /auth/session` when refresh fails with a 5xx; a proxied request whose refresh fails the same way |
| `chat_unavailable` | 503 | `POST /api/chat` with no usable `llm` configuration |
| `internal` | 500 | The gateway itself failed (sealing, config, decode) |

**Headers the gateway sets**, per host and on every response it produces — proxied, `302` to login, and JSON errors alike: `X-Frame-Options` (`DENY`, or `SAMEORIGIN` when the host has `frame: self`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and `Permissions-Policy` (host value or the default). `Strict-Transport-Security` is the proxy's, never here. Not on `101 Switching Protocols`: headers on a WebSocket handshake break the upgrade.

**Identity on the way upstream**, only on `identity: inject` hosts, after stripping whatever the client sent:

| Header | Source |
|---|---|
| `X-Auth-Subject` | `sub` |
| `X-Auth-Email`, `X-Auth-Name` | claims, omitted when empty |
| `X-Auth-Roles` | sorted, space separated |
| `X-Auth-Session` | `sid` |
| `Authorization: Bearer <access>` | the verified token |

`identity: passthrough` hosts (`id.filenkov.store`) get none of it: the client's own `Authorization` is forwarded untouched.

## Probes and metrics

`GET /healthz` — `200 {"status":"ok"}`. Answers for any host *except* one that routes a literal `/healthz` itself: `image.filenkov.store` declares `- { path: /healthz }`, so there it is the app's answer, not the gateway's.

`GET /readyz` — `200 {"status":"ready"}` or `503 {"error":"auth_unavailable"}`. It reports the last OIDC probe result: discovery plus JWKS loaded at least once. It does not probe product upstreams, and it does not re-probe the idp, so a dead idp can stay "ready" until `idp.jwks_ttl` expires.

`GET /metrics` on the public listener — always `404 not_found`. The real listener is `METRICS_ADDR` (`:9000` in the container, published to `127.0.0.1:19000`), and it is the only thing on it.

| Metric | Labels |
|---|---|
| `gateway_requests_total` | `host`, `route`, `policy`, `status` |
| `gateway_request_duration_seconds` | `host`, `route` |
| `gateway_token_refresh_total` | `result` |
| `gateway_idp_request_total` | `op`, `status` |
| `gateway_ws_active` | `host` |

Access log, one JSON line per proxied request: `ts`, `host`, `method`, `path`, `route`, `policy`, `status`, `dur_ms`, `sub`, `ip`, `ua`. Never tokens, codes, cookies, or `Authorization`.

## `/auth`

Four endpoints, apex only, mounted when a route is `bff: true`. Cookies: `HttpOnly; Secure; SameSite=Lax; Path=/; Domain=.filenkov.store`, name prefix `__Secure-`; `__Host-` is impossible with a `Domain`.

| Cookie | Contents | TTL |
|---|---|---|
| `__Secure-open_access` | Access JWT, unmodified | `session.access_ttl` (5m) |
| `__Secure-open_session` | AES-256-GCM of `{sub, refresh_token, sid}` | `session.idle_ttl` (168h) |
| `__Secure-open_flow` | `{state, nonce, code_verifier, return_to}` | 10m, login only |

### `GET /auth/login?return_to=`

1. `return_to` must be `https`, a host from `hosts`, or `public_origin`. Anything else redirects to `public_origin`.
2. Mint `state` (16 bytes), `nonce` (16 bytes), PKCE S256 `code_verifier`; seal the flow cookie.
3. `302` to the idp `/protocol/openid-connect/auth` with `client_id=gateway`, `redirect_uri=<public_origin>/auth/callback`, `response_type=code`, `scope=openid profile email`, `kc_idp_hint=google`, `state`, `nonce`, `code_challenge`, `code_challenge_method=S256`.

Request headers: none required. Answer: `302` only.

### `GET /auth/callback?code&state`

1. Compare `state` with `__Secure-open_flow`; delete the flow cookie whatever happens next.
2. Exchange the code (`authorization_code` + `client_secret` + `code_verifier`).
3. Check the `id_token`: JWKS signature, `iss`, `aud=gateway`, `nonce`, `exp`.
4. Set `__Secure-open_access` and `__Secure-open_session`; `sid` comes from the access token.
5. `302` to `return_to`.

On a bad state, a failed exchange, or a bad nonce: `302` to `public_origin/?auth_error=<code>`. Never an HTML error page.

### `GET /auth/session`

The SPA's only identity call. `200` when signed in:

```json
{
  "subject": "8f14e45f-ceea-467a-9e4b-1c2f9a0f5d11",
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "roles": ["admin", "svc:storage:family"],
  "services": [
    { "service": "storage", "level": "family" },
    { "service": "image", "level": "admin" }
  ]
}
```

`services` lists every key in `services:` in config order, `level: null` for no role. The page never parses role names. Anonymous: `401 {"error":"unauthorized"}`; if the refresh failed: `503 {"error":"auth_unavailable"}`.

### `POST /auth/logout`

Requires `Origin` matching `public_origin`, or `X-Requested-With` when the caller cannot send `Origin`; otherwise `403`. Body: none. Then logout at the idp with the refresh token from the cookie, delete the cookies, `200 {"status":"ok"}`.

There is no `GET /auth/logout`.

Refresh is not an endpoint: a request arriving with a stale access cookie triggers one token exchange per subject, its answer is reused for 30 seconds, new `Set-Cookie` is copied onto the original response and the request is retried. `400 invalid_grant` clears the session cookie and continues as anonymous.

## `/admin`

Four endpoints, apex only, `admin: true` routes. Not proxied; the gateway calls Keycloak for everything. Callers: the resume page's `/admin` UI, with the session cookie — no separate API key.

| Endpoint | `admin` | `svc:<svc>:admin` | others |
|---|---|---|---|
| `GET /admin/users` | yes | 403 | 403 |
| `PUT /admin/users/{id}/roles/{svc}` | any service | own `{svc}` only | 403 |
| `PATCH /admin/users/{id}` | yes | 403 | 403 |
| `PUT /admin/users/{id}/admin` | yes | 403 | 403 |

### `GET /admin/users`

No body. `200 { "users": [...], "total": N }`, each user `id`, `email`, `name`, `enabled`, `admin`, `services[{service, level}]`. Built live from the Admin API: one page of 200 users plus one role-mapping call each. No cache — above 200 accounts the list is short by contract, and the filter belongs in the Admin API, not in a local copy.

### `PUT /admin/users/{id}/roles/{svc}`

Body: `{ "level": "family" | "admin" | "blocked" | null }`. Every `svc:<svc>:*` on the user is removed, then the chosen one granted; `null` leaves the service closed to the user. `svc=admin` answers `400 validation` (that is a realm role, not a service); an unconfigured `svc` answers `404`. `200 {"status":"ok"}`.

### `PATCH /admin/users/{id}`

Body: `{ "enabled": false | true }`, the field is mandatory. Setting `false` is the global block: the user is updated and every session is logged out at the idp. Access tokens survive up to five minutes. Refusing to disable the last enabled `admin` answers `409 last_admin`; a repeat of the current value is a no-op, not a refusal. `200 {"status":"ok"}`.

### `PUT /admin/users/{id}/admin`

Body: `{ "value": true | false }`, the field is mandatory. `true` grants realm `admin`, `false` removes it. Removing it from the last admin answers `409 last_admin`, including a caller removing it from themselves. A repeat of the current value is a no-op. `200 {"status":"ok"}`.

## `/api/chat`

`POST /api/chat` on the apex, `policy: public`, answered in-process (`chat: true`, no upstream — [ADR-0009](../adrs/9-owl-chat-in-the-gateway.md)).

Request: `Content-Type: application/json`, body `{"question": "<text>"}`, at most 4 KiB. The question is trimmed, must be non-empty and at most 255 runes; anything else is `400` with the reason in `{"error": "..."}` — note this one endpoint answers a sentence, not a snake_case code, because the text goes straight to the page.

Optional header `X-Chat-Session`: an opaque client session id, letters/digits/`-_.`, max 64 chars. It is attribution for the logs, never a credential; a malformed value is replaced by a random UUID, and the request is still served.

Answer when configured: `200`, `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`. Frames:

```text
data: {"delta":"…"}
data: {"delta":"…"}
data: [DONE]
```

A failure after the headers are flushed travels as `data: {"error":"The owl could not reach its brain. Try again."}` — the status line is already spent. No `llm` block or no key: `503 {"error":"chat_unavailable"}` before any byte of stream.

Nothing is stored between requests: no history, no session state. A signed-in caller is identified by the verified cookie; an anonymous one is not identified at all.

## Proxied endpoints

### `GET /api/services`, `GET|POST|PUT|DELETE /api/services/**`

Proxied to the `switch` upstream. The gateway injects `X-Service-Token: <SWITCH_TOKEN>` as a request header; a client-supplied value is replaced, never merged. `GET /api/services` is `session`; the rest is `admin`. Switch is reached on its LAN address (`192.168.1.102:8095`) because `host.docker.internal` does not answer under rootless podman.

### Product hosts

`storage.`, `image.`, `rag.`, `audio.`, `llm.`, `observer.`, `id.`: everything not listed above is proxied to the host's upstream with the identity headers and the access token, `X-Forwarded-*` rewritten, `FlushInterval: -1` so SSE and token streams are not buffered, and no `WriteTimeout` so a WebSocket is not cut. The upstream's `101` is passed through untouched.

`id.` is `identity: passthrough`: the gateway forwards the client's `Authorization` and adds no identity header. Caddy admits that name only from the LAN and WireGuard list. `meet.filenkov.store` is not a gateway host.

## Startup rules

A config that breaks any of these fails the start; there is no warning-only mode ([ADR-0004](../adrs/4-config-fails-at-start.md)).

1. A host lacks exactly one `/**`, or `/**` is not last.
2. A route sits after that host's `/**`.
3. Two routes on one host share `path` and overlapping `methods`.
4. `upstream` is not in `upstreams`, unless the route is `bff` or `admin`.
5. `service(<svc>)` names a service outside `services`.
6. A value looks like a secret and is not `env:NAME`.
7. `aliases` overlap another host.
8. `strip_prefix` leaves an empty path.
9. `frame` is neither `deny` nor `self`.
10. `identity` is neither `inject` nor `passthrough`.
11. `idp.internal_url` is not an absolute `http`/`https` URL.
