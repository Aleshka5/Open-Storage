# gateway — external contract

What gateway requires, and the rules of talking to neighbors.

## Environment

| Variable | Required | Use |
|---|---|---|
| `GATEWAY_CONFIG` | yes | Path to `config.yaml` |
| `GATEWAY_SESSION_KEY` | yes | 32 bytes, base64. AES-GCM key for the session cookie. |
| `IDP_CLIENT_SECRET` | yes | Client `gateway` |
| `IDP_ADMIN_SECRET` | for `/admin` | Service account `gateway-admin` |
| `SWITCH_TOKEN` | for `/api/services` | Injected as `X-Service-Token` |
| `LLM_API_KEY` | for `/api/chat` | Injected upstream to LiteLLM |
| `LOG_LEVEL` | no | Default `info` |

A secret string in `config.yaml` fails startup. The file is in git.

## Identity provider

Issuer `https://id.filenkov.store/realms/filenkov`. Access tokens are RS256, `aud` contains `account`, `azp` is `gateway`. JWKS is cached by `kid` for 15 minutes and refreshed once on an unknown `kid`.

Gateway uses the authorization-code flow with PKCE S256 and a confidential client. It calls the token, revoke/logout, and Admin API endpoints. It does not sign tokens.

Role edits and "last admin" checks happen here because the Admin API service account is shared. See [Message-contract](API/Message-contract.md).

## Upstreams

Names resolve only on a shared Docker network. Attach a product network only when `upstreams` names a container on it. An extra network is extra attack surface.

Rate limit default: 600 requests per minute per IP, in process. One replica. Do not add a second counter in front of idp brute-force protection.

## Headers this service sets

| Header | Set by gateway | Note |
|---|---|---|
| `Permissions-Policy` | per host | Microphone and camera depend on the host |
| `X-Content-Type-Options`, `Referrer-Policy` | yes | |
| `X-Frame-Options: DENY` | yes, except `meet` and `audio` | Those apps frame themselves |
| `X-Forwarded-*` | rewritten | Must be the real host |
| Identity headers | injected after the strip | [identity v1](../external-contracts/identity-v1.md) |

`Strict-Transport-Security` is set by proxy, not here.

## Runtime invariants

| Invariant | If broken |
|---|---|
| `ForceAttemptHTTP2: false` toward upstreams | WebSocket upgrade fails |
| `FlushInterval: -1` on the reverse proxy | SSE and token streams buffer |
| No server `ReadTimeout` or `WriteTimeout` | Deadlines survive hijack and cut long WebSockets. `ReadHeaderTimeout` and `IdleTimeout` are safe. |
| Status wrapper implements `Hijack`, `Flush`, `Unwrap` | Upgrade breaks; status is not `101` |
| `ModifyResponse` returns immediately on `101` | Security headers on the handshake break the upgrade |
| No security headers on `Upgrade: websocket` | Same |
| Strip identity headers before injection and before proxy | A client can forge `X-Auth-Subject` |

Memory limit 128 MiB (about 48 MiB used). CPU limit 1. Gateway writes no disk.

## When it fails

| Symptom | Check |
|---|---|
| `404 {"error":"not_found"}` | Host or route missing. `curl -H 'Host: <fqdn>' http://127.0.0.1:8080/<path>` |
| `502 {"error":"bad_gateway"}` | Upstream name or port. `wget` that upstream from the gateway container. |
| Redirect loop on `/auth/login` | `redirect_uri` or cookie `Domain` / `Secure` / clock |
| `401` after a successful login | `aud` or `iss` disagrees with config |
| `403 {"error":"forbidden"}` for an expected user | `GET /auth/session` roles lack `svc:<svc>:family` |
| WebSocket dies within a minute | A `WriteTimeout` was added |
| Long upload returns `504` | Host `timeouts.response_header` |
| Every request slow | JWKS TTL expired; watch `gateway_idp_request_total` |
