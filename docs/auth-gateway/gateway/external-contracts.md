# gateway — external contracts

What the gateway needs from the outside, the endpoints of each neighbor it calls, and the invariants those calls depend on. The endpoints the gateway serves are in [API/api-contract.md](API/api-contract.md); its configuration and role are in [init.md](init.md).

Three neighbors: the identity provider, the product upstreams, and the LLM host behind the owl. Everything else it talks to is the browser.

## Identity provider

Keycloak. Realm facts, roles and lifetimes: [idp init](../idp/init.md). Endpoint shapes and bodies: [idp API contract](../idp/api-contract.md).

| Fact | Value |
|---|---|
| Issuer | `https://id.filenkov.store/realms/filenkov` |
| Server-side base | `idp.internal_url` when set (`http://idp:8080/realms/filenkov`), otherwise the issuer |
| Client | `gateway`, confidential, standard flow, PKCE S256, secret `IDP_CLIENT_SECRET` |
| Admin client | `gateway-admin`, service account, secret `IDP_ADMIN_SECRET` |
| Tokens | RS256. `aud` contains `account`, `azp` is `gateway` |
| JWKS cache | by `kid`, 15 minutes (`idp.jwks_ttl`), one refetch on an unknown `kid` |

The gateway is the OIDC client: it does not sign tokens and it does not accept an idp token from a client. Every endpoint it uses, what it sends, and what it expects back:

| Method | Path | Body / query the gateway sends | Answer it requires |
|---|---|---|---|
| `GET` | `/.well-known/openid-configuration` | — | `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`; cached at start, a missing answer fails startup |
| `GET` | `/protocol/openid-connect/certs` | — | JWKS keyed by `kid`; `503` handling below |
| `POST` | `/protocol/openid-connect/token` | `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `client_secret`, `code_verifier` | `200` with `access_token`, `refresh_token`, `id_token`, `expires_in` |
| `POST` | `/protocol/openid-connect/token` | `grant_type=refresh_token`, `refresh_token`, `client_id`, `client_secret` | same, new refresh token |
| `POST` | `/protocol/openid-connect/token` | `grant_type=client_credentials`, `client_id=gateway-admin`, `client_secret` | `200` with `access_token` for the Admin API |
| `POST` | `/protocol/openid-connect/logout` | `client_id`, `client_secret`, `refresh_token` | `2xx`; `>=400` is a reported failure, not a silent one |
| `GET` | `/admin/realms/filenkov/users?first=0&max=200` | bearer from `client_credentials` | the roster; stopped at 200 by contract |
| `GET` | `/admin/realms/filenkov/users/{id}` | — | the whole account object; read before any `PUT` |
| `PUT` | `/admin/realms/filenkov/users/{id}` | the full object with `enabled` changed | `2xx`. It replaces, so it is read-modify-write |
| `POST` | `/admin/realms/filenkov/users/{id}/logout` | — | `2xx`; used on block, downgrade and explicit sign-out |
| `GET` | `/admin/realms/filenkov/users/{id}/role-mappings/realm` | — | `[{id, name}]` |
| `POST` | `/admin/realms/filenkov/users/{id}/role-mappings/realm` | `[{id, name}]` | grant |
| `DELETE` | `/admin/realms/filenkov/users/{id}/role-mappings/realm` | `[{id, name}]` | revoke; a no-op revoke is `204`, so it is safe to repeat |
| `GET` | `/admin/realms/filenkov/roles` | — | the catalog, to resolve a role name to an `id` before mapping |
| `GET` | `/admin/realms/filenkov/roles/admin/users?first=0&max=50` | — | the "last admin" guard counts enabled members |

The browser's two legs — `/protocol/openid-connect/auth` and the `GET /logout` — are the proxy's and idp's business; the gateway only builds the `302`.

**What each failure becomes.** A token endpoint `400 invalid_grant` on refresh clears the session cookie and continues as anonymous. Any Admin API error that is not a `404` (unknown user) maps to `503 idp_unavailable`; a `401`/`403` there is a secret or service-account defect, not an authorization decision by the gateway. A JWKS refetch that fails leaves the old keys in place and `/readyz` red — sign-in still works for a cached `kid` until the TTL expires.

**Why the single refresh.** Keycloak rotates refresh tokens with no reuse tolerance (`revokeRefreshToken`, `refreshTokenMaxReuse: 0`), so a second exchange of the same token is theft by its rules. The gateway allows one exchange per `sub` in flight, reuses the answer for 30 seconds, and copies the `Set-Cookie` onto the original response before retrying. Two tabs refreshing at once must get the finished answer, not a second exchange, or both are signed out.

## LLM host

The owl's model, called from `POST /api/chat` with `llm.host`, `llm.api_key`, `llm.model`, `llm.reasoning_effort`, `llm.timeout`; `LLM_HOST`, `LLM_MODEL`, `LLM_REASONING_EFFORT` override the file, and a missing key leaves the route `503` without touching anything else.

Contract: OpenAI-compatible `POST <host>/chat/completions`, `stream: true`, `Accept: text/event-stream`, `Authorization: Bearer <key>`. The gateway forwards each delta as an SSE frame and writes `[DONE]` itself. An `llm` block that names no host or no model disables the route, not the process.

Tracing: with `MLFLOW_TRACING_ENDPOINT` set (and `MLFLOW_EXPERIMENT_ID` required alongside it), the chat exports OTLP spans to MLflow; unset means no exporter and no startup change.

## Runtime invariants

| Invariant | If broken |
|---|---|
| `ForceAttemptHTTP2: false` toward upstreams | WebSocket upgrade fails |
| `FlushInterval: -1` on the reverse proxy | SSE and token streams buffer |
| No server `ReadTimeout` or `WriteTimeout` | Deadlines survive hijack and cut long WebSockets; `ReadHeaderTimeout` and `IdleTimeout` are safe |
| The status wrapper implements `Hijack`, `Flush`, `Unwrap` | Upgrade breaks; status is not `101` |
| `ModifyResponse` returns immediately on `101` | Security headers on the handshake break the upgrade |
| Identity headers are stripped before injection and before proxy | A client forges `X-Auth-Subject` |
| One refresh in flight per `sub`, answer reused 30s | Two tabs sign each other out |
| One replica | The in-process rate limit (600/min/IP) doubles and refreshes race |

## When it fails

| Symptom | Check |
|---|---|
| `404 {"error":"not_found"}` | Host or route missing. `curl -H 'Host: <fqdn>' http://127.0.0.1:8083/<path>` |
| `502 {"error":"bad_gateway"}` | Upstream name or port. `wget` that upstream from the gateway container |
| Redirect loop on `/auth/login` | `redirect_uri`, or cookie `Domain` / `Secure` / clock |
| `401` after a successful login | `aud` or `iss` disagrees with config |
| `403 {"error":"forbidden"}` for an expected user | `GET /auth/session` roles lack `svc:<svc>:family` |
| WebSocket dies within a minute | A `WriteTimeout` was added |
| Long upload returns `504` | Host `timeouts.response_header` |
| Every request slow | JWKS TTL expired; watch `gateway_idp_request_total` |
| `/readyz` red while sign-in still works | idp unreachable at the last JWKS load; cached keys still serve |
