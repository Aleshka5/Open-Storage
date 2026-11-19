# gateway — message contract

What callers get. Identity headers shared with product apps are owned by [identity v1](../../external-contracts/identity-v1.md). This file owns routes, policies, `/auth`, and `/admin`.

Listen `:8080`. Config is `config.yaml`, read only at start. A change is a restart. No hot reload.

## Policies

| Expression | Allows |
|---|---|
| `public` | Everyone, including anonymous |
| `session` | An authenticated account that is enabled |
| `admin` | Realm role `admin` only |
| `service(<svc>)` | `svc:<svc>:family` or `svc:<svc>:admin`. Includes session. |
| `service(<svc>, admin)` | `svc:<svc>:admin` only |
| `deny` | Nobody. The path answers `404`, as if absent. |

`svc:<svc>:blocked` beats `session` on a host whose policy is `session`.

Anonymous browser navigation: `302` to `/auth/login?return_to=…`. Anonymous `/api/*`, `/users*`, and WebSocket: `401` JSON. No route, including `deny`: `404` JSON.

## Route

First match wins. Specific routes go above general ones. Each host has exactly one `/**`, and it is last.

```yaml
- path: /api/**                 # literal, /prefix/**, or /**
  methods: [GET, POST]          # default: all
  policy: session               # required
  upstream: audio               # optional override of the host upstream
  strip_prefix: /api
  bff: true                     # internal /auth/*
  admin: true                   # internal /admin/*
  inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" }
  timeouts: { response_header: 30m }
```

A host also carries `frame: self` when its own UI frames itself (Jitsi Meet, the ASR UI). The default is `deny`, which sends `X-Frame-Options: DENY`; the choice belongs to the host entry, not to a prefix of its name.

`identity: passthrough` marks a host that is not an application under identity v1 — today only `id.filenkov.store`, the idp's own console. On such a host nothing is stripped and nothing is injected: the client's own `Authorization` is what the upstream needs. Every other host is `inject` (the default) and never sees a header the client sent.

`response_header` is time to the first response byte, not the life of the body. SSE and WebSocket length are not capped by it.

`service:` on a host names the service that owns it. With it set, `svc:<service>:blocked` closes every non-public route on that host, including a `session` catch-all. Without it, `blocked` only denies `service(...)` routes.

Fail start when:

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

## Hosts

`services` (per-service roles, and therefore `/admin` columns): `storage`, `image`, `rag`, `audio`. Hub, llm, observer, and meet use `public`, `admin`, or `session` only.

```yaml
listen: ":8080"
public_origin: "https://filenkov.store"
idp:
  issuer: "https://id.filenkov.store/realms/filenkov"
  # Optional. Where this process reaches the idp; discovery, JWKS, token, logout
  # and the Admin API go here, the browser still follows the public endpoints and
  # `iss` stays the public issuer. Set it to the container address so a start does
  # not depend on the LAN resolver answering for the public host.
  internal_url: "http://idp:8080/realms/filenkov"
  client_id: gateway
  client_secret: "env:IDP_CLIENT_SECRET"
  scopes: [openid, profile, email]
  audience: account
  authorized_party: gateway
  jwks_ttl: 15m
session:
  cookie_domain: ".filenkov.store"
  access_ttl: 5m
  idle_ttl: 168h
  key: "env:GATEWAY_SESSION_KEY"
admin:
  client_id: gateway-admin
  client_secret: "env:IDP_ADMIN_SECRET"
services: [storage, image, rag, audio]
defaults:
  timeouts: { connect: 5s, read_header: 15s, response_header: 60s, idle: 120s }
  rate_limit: { requests: 600, per: 1m }
upstreams:
  resume: "resume:80"
  idp: "idp:8080"
  storage: "app:8000"
  image: "qwen-image:8000"
  llm: "qwen38:4001"
  rag: "rag-edge:8080"
  audio: "audio-api:8000"
  audio_web: "frontend:80"
  grafana: "grafana:3000"
  jitsi: "jitsi-web:8000"
  switch: "192.168.1.102:8095"
  litellm: "litellm-proxy-server:4000"
hosts:
  - host: filenkov.store
    upstream: resume
    routes:
      - { path: /auth/**, bff: true }
      - { path: /admin/**, admin: true, policy: admin }
      - { path: /api/chat, methods: [POST], upstream: litellm, policy: public,
          inject_headers: { X-Api-Key: "env:LLM_API_KEY" }, timeouts: { response_header: 60s } }
      - { path: /api/services, methods: [GET], upstream: switch, policy: session,
          inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      - { path: /api/services/**, upstream: switch, policy: admin,
          inject_headers: { X-Service-Token: "env:SWITCH_TOKEN" } }
      - { path: /users/**, policy: deny }
      - { path: /**, upstream: resume, policy: public }
  - host: id.filenkov.store
    upstream: idp
    routes:
      - { path: /**, policy: public }          # Keycloak console stays reachable for break-glass
  - host: storage.filenkov.store
    upstream: storage
    timeouts: { response_header: 30m }
    routes:
      - { path: /health, policy: public }
      - { path: /**, policy: "service(storage, family, admin)" }
  - host: image.filenkov.store
    upstream: image
    timeouts: { response_header: 30m }
    routes:
      - { path: /healthz, policy: public }
      - { path: /**, policy: "service(image, family, admin)" }
  - host: rag.filenkov.store
    upstream: rag
    timeouts: { response_header: 5m }
    routes:
      - { path: /health, policy: public }
      - { path: /**, policy: "service(rag, family, admin)" }
  - host: audio.filenkov.store
    upstream: audio_web
    permissions_policy: "camera=(), microphone=(self), geolocation=()"
    timeouts: { response_header: 30m }
    routes:
      - { path: /health, upstream: audio, policy: public }
      - { path: /api/**, upstream: audio, policy: "service(audio, family, admin)" }
      - { path: /**, policy: session }
  - host: llm.filenkov.store
    upstream: llm
    timeouts: { response_header: 10m }
    routes:
      - { path: /**, policy: admin }
  - host: observer.filenkov.store
    upstream: grafana
    timeouts: { response_header: 5m }
    routes:
      - { path: /api/health, policy: public }
      - { path: /**, policy: session }
  - host: meet.filenkov.store
    upstream: jitsi
    permissions_policy: "camera=(self), microphone=(self), display-capture=(self), geolocation=()"
    timeouts: { response_header: 5m }
    routes:
      - { path: /**, policy: session }
```

A new host needs an `upstreams` entry, a `hosts` block with `/**`, a `services` entry when it has roles, a proxy site block, and a DNS name.

## `/auth`

Cookies: `HttpOnly; Secure; SameSite=Lax; Path=/; Domain=.filenkov.store`. Prefix `__Secure-` because the cookie must cross subdomains. `__Host-` forbids `Domain`.

| Cookie | Contents | TTL |
|---|---|---|
| `__Secure-open_access` | Access JWT, unmodified | `session.access_ttl` (5m) |
| `__Secure-open_session` | AES-256-GCM of `{sub, refresh_token, sid}` | `session.idle_ttl` (168h) |
| `__Secure-open_flow` | `{state, nonce, code_verifier, return_to}` | 10m, login only |

No roles and no email in the session cookie. Roles are read from the access token on every request. Rotating `GATEWAY_SESSION_KEY` signs everyone out.

One refresh runs at a time per session cookie, and its answer is reused for 30 seconds. The idp rotates refresh tokens with no reuse tolerance (`revokeRefreshToken`, `refreshTokenMaxReuse: 0`), so a second exchange of the same token is theft in its eyes: a request that was already in flight with the old cookie has to get the finished answer, not a new exchange. Without that window, two tabs opened at the same moment sign the user out.

`GET /auth/login?return_to=`

1. `return_to` must be `https` and a host from `hosts`, or `public_origin`. Otherwise redirect to `public_origin`.
2. Mint `state` (16 bytes), `nonce` (16 bytes), PKCE S256 `code_verifier`.
3. `302` to the idp authorization endpoint with `client_id=gateway`, `redirect_uri=https://filenkov.store/auth/callback`, `response_type=code`, `scope=openid profile email`, `kc_idp_hint=google`, `state`, `nonce`, `code_challenge`.

`GET /auth/callback?code&state`

1. Compare `state` to `__Secure-open_flow`, then delete that cookie.
2. Exchange the code (`authorization_code`, `client_secret`, `code_verifier`).
3. Check `id_token`: JWKS signature, `iss`, `aud=gateway`, `nonce`, `exp`.
4. Set access and session cookies. `sid` comes from the access token.
5. `302` to `return_to`.

On `invalid state`, a failed exchange, or a bad `nonce`: `302` to `public_origin/?auth_error=<code>`. No HTML error to the browser.

`GET /auth/session` — public route. `200` only when signed in.

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

Anonymous: `401 {"error":"unauthorized"}`. `services` lists every key in `services:`. The page does not parse role names.

`POST /auth/logout`

1. Require `Origin` or `X-Requested-With`, else `403`.
2. Logout at idp with the refresh token from the cookie.
3. Delete cookies. `200 {"status":"ok"}`.

There is no `GET /auth/logout`.

Refresh: one token exchange per `sub` at a time. Parallel requests wait. Copy new `Set-Cookie` onto the original response, then retry the request. `400 invalid_grant` clears the session cookie and continues as anonymous.

## `/admin`

Handled inside gateway on `filenkov.store`. Not proxied.

| Endpoint | `admin` | `svc:<svc>:admin` | others |
|---|---|---|---|
| `GET /admin/users` | yes | 403 | 403 |
| `PUT /admin/users/{id}/roles/{svc}` | any service | own `{svc}` only | 403 |
| `PATCH /admin/users/{id}` | yes | 403 | 403 |
| `PUT /admin/users/{id}/admin` | yes | 403 | 403 |

`GET /admin/users` returns `{ users, total }`. Each user: `id`, `email`, `name`, `enabled`, `admin`, `services`. `services` always lists every `services:` key; `level: null` means no role. Order follows config. Built from Keycloak `GET /admin/realms/filenkov/users?first=0&max=200` plus one role-mapping call per user. No cache. Above 200 users, filter via the Admin API. Do not copy the catalog locally.

`PUT /admin/users/{id}/roles/{svc}` body: `{ "level": "family" | "admin" | "blocked" | null }`. Remove every `svc:<svc>:*` on that user, then grant the chosen level. One role per service.

`PATCH /admin/users/{id}` body: `{ "enabled": false }`. Updates the user and logs their sessions out. Access tokens die within 5 minutes.

`PUT /admin/users/{id}/admin` body: `{ "value": true }`. Caller must hold `admin`. Refusing to remove `admin` from the last admin returns `409`. A caller cannot remove `admin` from themselves when they are the last admin. `svc=admin` on the service-role path returns `400`.

One envelope for the edge and for `/admin`: `{"error":"<snake_case>"}` ([ADR-0005](../../adrs/0005-port-from-auth-service.md)).

```json
{ "error": "last_admin" }
```

| Value | HTTP | When |
|---|---|---|
| `unauthorized` | 401 | No session, or the session expired and could not be refreshed |
| `forbidden` | 403 | Signed in, role does not allow |
| `not_found` | 404 | Unknown user id |
| `validation` | 400 | Bad body, or `svc=admin` on the service-role path |
| `last_admin` | 409 | The change would leave no realm `admin` |
| `idp_unavailable` | 503 | Keycloak Admin API did not answer |

## Probes

| Path | Meaning |
|---|---|
| `GET /healthz` | Process up, config valid |
| `GET /readyz` | idp discovery and JWKS loaded, else `503`. Does not check product upstreams. |
| `GET /metrics` | Prometheus, on a second listener (`METRICS_ADDR`, default `:9000`) that is published to host loopback only. The public port answers `404`. |

Metrics: `gateway_requests_total{host,route,policy,status}`, `gateway_request_duration_seconds{host,route}`, `gateway_token_refresh_total{result}`, `gateway_idp_request_total{op,status}`, `gateway_ws_active{host}`.

Access log, one JSON line: `ts, host, method, path, route, policy, status, dur_ms, sub, ip, ua`. Never log tokens, codes, cookies, or `Authorization`.
