# gateway — init

What the gateway is, how it runs, and the configuration it refuses to start without. The endpoints it serves are in [api-contract.md](api-contract.md); the endpoints it calls and the invariants of those calls are in [external-contracts.md](external-contracts.md).

## Purpose

The gateway is the edge's one Go process: BFF for login, route policy, identity injection, the reverse proxy to every product upstream, `/admin`, and the owl chat answered in-process. It is the only place in the namespace that knows which host may call which application.

It stores nothing. Users, roles, sessions and tokens are Keycloak's; the session cookie holds an encrypted Keycloak refresh token, and the Keycloak session is the session. Restarting the gateway does not sign anyone out; rotating `GATEWAY_SESSION_KEY` does ([ADR-0002](../adrs/2-bff-in-the-gateway.md)).

| Fact | Value |
|---|---|
| Stack | Go 1.26, stdlib, `gopkg.in/yaml.v3`, `coreos/go-oidc/v3`, `go-jose/v4` |
| Public listener | `:8080` inside the container. [`.env.example`](../../../deploy/auth-gateway/.env.example) sets `GATEWAY_PORT=8083`, and the Makefile declares the same default. Compose falls back to `8080` only when the variable is unset. |
| Metrics listener | `METRICS_ADDR`, default `:9000`, published as `127.0.0.1:${METRICS_PORT:-19000}` |
| Config | `GATEWAY_CONFIG`, a YAML file read once at start ([ADR-0004](../adrs/4-config-fails-at-start.md)) |
| State | none on disk |
| Limits | compose `mem_limit: 160m`. No CPU limit in compose. |
| Budget | 5500 lines of Go, tests excluded ([ADR-0010](../adrs/10-gateway-line-budget.md)) |
| Compose | `deploy/auth-gateway/docker-compose.yaml`, service `gateway`, network `open_network` plus product networks |

One replica. The rate limit is in-process, and a second replica would double it and race the single refresh per subject.

## Role in the namespace

```text
browser --TLS--> proxy --http--> gateway --http--> resume, idp, storage, image, rag, audio, llm, grafana, switch
                                    |
                                    +-- OIDC client --> idp (discovery, JWKS, token, logout)
                                    +-- Admin API  --> idp (users, role mappings, sessions)
                                    +-- chat       --> llm host (OpenAI-compatible, SSE)
```

The proxy terminates TLS. The SSO hosts and `id.` share `127.0.0.1:8083`. `id.` is public ([ADR-0013](../adrs/13-idp-host-public.md)). `meet.` does not reach the gateway. On the hosts that do, the `Host` header picks the block. Product apps receive the [identity v1](../external-contracts/identity-v1.md) headers and their own `Bearer` access token, and never see a header the client sent.

## Configuration

`config.yaml` is committed. Secrets are `env:NAME` references only; a literal that looks like a secret fails startup. Shape:

| Block | What it fixes |
|---|---|
| `listen`, `public_origin` | Tie-break for `return_to`, the callback URL, and the post-logout redirect |
| `idp` | Issuer, optional `internal_url` for server-side calls, client id/secret, scopes, `audience`, `authorized_party`, `jwks_ttl` |
| `session` | Cookie domain, access TTL, idle TTL, the AES-256-GCM key |
| `admin` | The `gateway-admin` service account |
| `services` | The services that have roles. Drives `/admin` columns and `service(...)` validity |
| `defaults` | Timeouts and the in-process rate limit |
| `upstreams` | Name to `host:port`. A route may name only these |
| `llm` | The owl's host, key, model, reasoning effort, timeout. Optional as a whole |
| `hosts` | One block per host: upstream, optional `service`, `frame`, `identity`, `permissions_policy`, `timeouts`, routes |

A route is `path`, `methods`, `policy`, and optionally `upstream`, `strip_prefix`, `bff`, `admin`, `chat`, `inject_headers`, `timeouts`. First match wins; each host has exactly one `/**` and it is last.

Routes are matched against the path the proxy forwarded, so a route's `policy` is the only authorization decision in the namespace. Policies: `public`, `session`, `admin`, `service(<svc>)`, `service(<svc>, admin)`, `deny`. `deny` answers `404`, not `403`: a hidden path and a missing one look identical.

Eleven rules fail the start rather than degrade: no `/**`, `/**` not last, overlapping routes, unknown upstream, unknown service, a secret in the file, overlapping aliases, an empty `strip_prefix`, a bad `frame`, a bad `identity`, a relative `idp.internal_url`. The full list is in the [API contract](api-contract.md#startup-rules) beside the surface it protects.

## Product upstreams

Named in `upstreams`, reached by container name on a shared Docker/podman network, or by LAN address when the service runs on the host. One upstream per host; a route may override it. Policies and the header set are in [identity v1](../external-contracts/identity-v1.md) and the [API contract](api-contract.md).

| Upstream | Address | Host | Needs |
|---|---|---|---|
| `resume` | `resume:80` | apex | static files; `/auth`, `/admin`, `/api/chat` are the gateway's own |
| `idp` | `idp:8080` | `id.` | passthrough headers; no identity |
| `storage` | `app:8000` | `storage.` | identity v1, `Bearer` |
| `image` | `qwen-image:8000` | `image.` | identity v1; serves its own `/healthz` |
| `rag` | `rag-edge:8080` | `rag.` | identity v1 |
| `audio` / `audio_web` | `audio-api:8000` / `frontend:80` | `audio.` | identity v1 on `/api/**`, session on the UI |
| `llm` | `qwen38:4001` | `llm.` | `admin` policy, raw vLLM-style endpoint |
| `grafana` | `grafana:3000` | `observer.` | session; Grafana's own login still applies |
| `switch` | `192.168.1.102:8095` | apex `/api/services` | `X-Service-Token` injected by the gateway |
| `litellm` | `litellm-proxy-server:4000` | apex `POST /api/chat` | not used: the chat goes through the `llm` block, not this upstream ([ADR-0009](../adrs/9-owl-chat-in-the-gateway.md)) |

Networks: `open_network` for the namespace's own services, plus `models_network`, `rag_network`, `audio_network`, `deploy_auth_network` — only those the `upstreams` table actually names. An extra network is extra attack surface. The gateway does not join `common_network`. `audio_network` is created by the [audio](../../audio/init.md) namespace and declared external here, the same attachment as `rag_network` ([ADR-0011](../../../adrs/11-gateway-joins-rag-network.md)). Postgres, Redis, MinIO, RabbitMQ and Mongo run in the [common](../../common/init.md) namespace. The storage app joins that network itself ([open-storage init](../../open-storage/init.md)).
Adding a host is one change in four places: `upstreams` and a `hosts` block here, a `services` entry when it has roles, a proxy site block, and a DNS name. A service with roles also needs `svc:<name>:{admin,family,blocked}` in the realm ([idp init](../idp/init.md)).

## Identity

Two header sets, one direction. Client-supplied identity headers are stripped before anything is injected, and the injection is skipped on `identity: passthrough` hosts. Roles come from the access token on every request, not from the cookie; the session cookie holds no roles and no email.

The session cookie is `__Secure-open_session`: AES-256-GCM of `{sub, refresh_token, sid}`. Access is `__Secure-open_access`, the Keycloak JWT unmodified. The flow cookie holds `state`, `nonce`, `code_verifier` for ten minutes. `__Host-` is impossible because the cookie must cross subdomains.

## Probes and observability

`GET /healthz` is the gateway probe, except on a host that routes a literal `/healthz` itself (`image.filenkov.store`). `GET /readyz` reports whether discovery and the JWKS loaded (it does not check product upstreams), and `/metrics` answers only on the second listener — the public port answers `404`. Metric names and the access-log fields are fixed in the [API contract](api-contract.md#probes-and-metrics).

Readiness is the OIDC probe error cached from the last JWKS load, and the JWKS is reloaded on the TTL, so `/readyz` can lag a dead idp by up to `idp.jwks_ttl` (15m). It is a "did we ever load keys" answer, not a live reachability check.
