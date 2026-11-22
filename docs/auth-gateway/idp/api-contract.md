# idp — API contract

The endpoints Keycloak serves that this namespace depends on, and the shape of each request and answer. Realm facts (roles, lifetimes, clients, bootstrap) are in [init.md](../init.md); the Keycloak process itself is in the [external contract](external-contract.md).

Base: `https://id.filenkov.store`, a real realm `filenkov`. Server-side callers can use `http://idp:8080` on `open_network` instead; the issuer in the answers stays the public URL, because `KC_HOSTNAME` is fixed.

Every issue here except the browser's is made by the gateway. Keycloak serves the operations; the gateway decides who may start one. A `401`/`403` from the Admin API is therefore a gateway configuration defect, not an authorization decision.

## Endpoint inventory

| Method | Path | Caller | Answered by |
|---|---|---|---|
| `GET` | `/.well-known/openid-configuration` | gateway | This document |
| `GET` | `/protocol/openid-connect/auth` | Browser, redirected by gateway | The login flow |
| `POST` | `/protocol/openid-connect/token` | gateway | Code exchange, refresh, service account |
| `GET` | `/protocol/openid-connect/certs` | gateway | JWKS |
| `GET` | `/protocol/openid-connect/logout` | Browser, redirected by gateway | Local logout |
| `POST` | `/protocol/openid-connect/logout` | gateway | Ends the session tied to a refresh token |
| `GET` | `/protocol/openid-connect/userinfo` | nobody | The access token carries every claim we read |
| `GET` | `/broker/google/endpoint` | Google | The broker, registered as Google's redirect URI |
| `GET` | `/broker/google/login` | nobody | `kc_idp_hint=google` on `/auth` does it |
| `GET` | `/protocol/openid-connect/login-status-iframe.html` | Browser | Session polling. Needs `X-Frame-Options: SAMEORIGIN` on the host ([ADR-0008](../adrs/8-idp-host-frame-self.md)). |
| `GET` | `/health/ready`, `/health/live` | nobody yet | Management endpoints; **not reachable** on the `id.` host today |
| `GET` | `/admin/realms/filenkov/…` | gateway, `grant-admin.sh` | Admin API, below |

The admin console and the login theme are HTML surfaces on the same host, reached through the gateway with `identity: passthrough`, not part of this contract.

## Discovery

`GET /realms/filenkov/.well-known/openid-configuration` — no headers, no parameters.

Gateway reads `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint` and probes it at start (a missing answer fails startup, [ADR-0004](../adrs/4-config-fails-at-start.md)). Answers cached per `kid`, not per request.

The answer is the generic Keycloak list, wider than what this realm uses: `grant_types_supported` advertises `password`, `implicit`, `client_credentials`, `device_code`, `token-exchange` and `uma-ticket`; `id_token_signing_alg_values_supported` lists `HS256` through `EdDSA`. None of it is reachable with the two clients here — both are confidential, `gateway` allows only the standard flow and `gateway-admin` only the service account — and the gateway accepts `RS256` only. The advertisement is not the policy.

## Login

`GET /realms/filenkov/protocol/openid-connect/auth`

Query, built by the gateway, all of it required:

| Parameter | Value |
|---|---|
| `client_id` | `gateway` |
| `redirect_uri` | `https://filenkov.store/auth/callback` (`https://mvp.filenkov.store/auth/callback` on the MVP stand) |
| `response_type` | `code` |
| `scope` | `openid profile email` |
| `state` | 16 random bytes, compared to `__Secure-open_flow` on return |
| `nonce` | 16 random bytes, checked inside `id_token` |
| `code_challenge`, `code_challenge_method` | PKCE `S256` |

`kc_idp_hint=google`: a **Keycloak** parameter, not a Google one. It picks the broker and suppresses the Keycloak username form. A name that matches no identity provider in the realm is not an error; Keycloak falls back to the form, which is why the theme matters.

`redirect_uri` not in the client's list answers `400 Invalid parameter: redirect_uri` before anything else happens. The list is in `realm.json`, so adding a host is a realm change, not a gateway change.

Answers: `302` to Google through `/broker/google/endpoint`, or, without `kc_idp_hint`, the Keycloak form in theme `filenkov`.

## Token

`POST /realms/filenkov/protocol/openid-connect/token`

`Content-Type: application/x-www-form-urlencoded`. No bearer header: the client authenticates in the body.

| `grant_type` | Body | Caller |
|---|---|---|
| `authorization_code` | `code`, `redirect_uri`, `client_id=gateway`, `client_secret`, `code_verifier` | gateway, `/auth/callback` |
| `refresh_token` | `refresh_token`, `client_id=gateway`, `client_secret` | gateway, session refresh |
| `client_credentials` | `client_id=gateway-admin`, `client_secret` | gateway and `scripts/grant-admin.sh`, for an Admin API token |

Answer, `200`:

| Field | Shape | Note |
|---|---|---|
| `access_token` | RS256 JWT | `aud` contains `account` via a mapper; `azp` is `gateway`; `realm_access.roles` carries the `svc:*` and `admin` roles |
| `refresh_token` | opaque | Rotates. `revokeRefreshToken: true`, `refreshTokenMaxReuse: 0`: a second exchange of the same token is treated as theft and ends the session. That is why the gateway holds one refresh in flight per session cookie. |
| `id_token` | RS256 JWT | Returned on the code exchange only. `nonce`, `aud=gateway`, `iss` are checked |
| `expires_in` | `300` | Access token lifetime. It cannot be revoked. |
| `token_type`, `scope`, `session_state` | | `session_state` is the `sid` the gateway keeps in the session cookie |

Failures: `400 invalid_grant` (code reused, expired, or PKCE mismatch; refresh rotated away), `401 invalid_client` (secret disagrees with `realm.json`), `400 invalid_scope`. The gateway turns each of them into a sign-out, not an error page, unless the failure is on the token endpoint during a request that had a live cookie.

## JWKS

`GET /realms/filenkov/protocol/openid-connect/certs` — no headers.

`{"keys":[{kty, kid, alg:"RS256", use:"sig", n, e, x5c, x5t, ...}]}`. The gateway caches by `kid` for 15 minutes and refetches once when it meets an unknown `kid`, which is what a key rotation looks like from the outside.

## Logout

Two endpoints, two different jobs, both ending a session:

`GET /realms/filenkov/protocol/openid-connect/logout?id_token_hint=&post_logout_redirect_uri=` — browser, from the gateway's `302`. Ends the Keycloak session in the browser's cookie. `post_logout_redirect_uri` must be registered on the client; `realm.json` registers none, so the gateway sends no `post_logout_redirect_uri` and Keycloak shows its own page.

`POST /realms/filenkov/protocol/openid-connect/logout` — gateway, `application/x-www-form-urlencoded`, body `client_id=gateway`, `client_secret`, `refresh_token`. This is the one the gateway relies on when a session must die without the browser's help. `204` or `200` on success; `>=400` is a failed logout and the gateway reports it rather than pretending the refresh token is dead.

Access tokens survive either call for up to five minutes. There is no revocation list; a token stays valid until `exp`.

## Broker

`GET /realms/filenkov/broker/google/endpoint` — **Google's** redirect URI. It is the only URI registered on the Google OAuth client ([external contract](external-contract.md)).

Query on return: `code`, `state`, `scope`, `authuser`, `prompt`. Keycloak validates `state` itself and answers `400` with `invalid_request` or `invalid_state` on a mismatch; the user sees the Keycloak error page, not the gateway's.

Then: first broker login creates or links the account (`syncMode: IMPORT`, `sub` stays Google's subject forever; `FORCE` would change it on every login), roles come from `realm.json`, and the browser is sent back to the gateway's `redirect_uri` with the authorization `code`.

## Admin API

Prefix `/admin/realms/filenkov`. `Authorization: Bearer <token>`, client `gateway-admin`, service account with realm-management roles `view-users`, `manage-users`, `query-users`, `view-realm`.

| Method | Path | Body | Used for |
|---|---|---|---|
| `GET` | `/users?first=0&max=200` | — | The roster behind `/admin/users`. Stops at 200 by contract |
| `GET` | `/users/{id}` | — | The account object as Keycloak holds it, for the read-modify-write on `enabled` |
| `PUT` | `/users/{id}` | the full user object | Set `enabled`, which is the global block |
| `POST` | `/users/{id}/logout` | — | Drop every session: the block, a role downgrade, an operator's explicit sign-out |
| `GET` | `/users/{id}/role-mappings/realm` | — | Current realm roles of one user |
| `POST` | `/users/{id}/role-mappings/realm` | `[{id, name}]` | Grant roles |
| `DELETE` | `/users/{id}/role-mappings/realm` | `[{id, name}]` | Revoke roles |
| `GET` | `/roles` | — | The realm role catalog, used to resolve a name to an `id` before a mapping call |
| `GET` | `/roles/admin/users?first=0&max=50` | — | The "last admin" guard: counts enabled members |

`PUT /users/{id}` replaces the object, so the gateway reads it first. There is no patch and no cache.

`grant-admin.sh` takes the one route the gateway does not: `GET /users?exact=true&email=<address>`, then `GET /roles/admin`, then `POST /users/{id}/role-mappings/realm`. Same service account, same token endpoint. It is the only caller of the Admin API outside the gateway.

`DELETE` on a mapping that is not present answers `204` and does nothing, so revoking twice is safe. Mapping a role whose `id` belongs to another realm answers `404`.

## Health

`KC_HEALTH_ENABLED=true` is set, but the management endpoints are not published on the `id.` host: `GET /realms/filenkov/health/ready`, `/health/ready`, and `/health` all answer `404 {"error":"HTTP 404 Not Found"}` — the gateway's envelope, so the gateway answered, which means it has no such route on that host. Keycloak's health listener is on port 9000 inside the container (already taken by the metrics listener in this compose file), not 8080, and nothing in compose publishes it.

Readiness is therefore observed, not probed: `gateway_idp_request_total` on the gateway's metrics listener (`127.0.0.1:19000/metrics`), and the first request that needs a token. Do not document a probe URL that answers `404`, and do not add `/health` to the `id.` host without checking which process will answer it.

## When it fails

| Symptom | Check |
|---|---|
| `400 Invalid parameter: redirect_uri` | The host's `/auth/callback` is missing from the `gateway` client's redirect list |
| `400 invalid_grant` on refresh, everyone signed out at once | Two consumers exchanging one refresh token, or `revokeRefreshToken` turned off so an old token never dies |
| Login works, `realm_access.roles` empty | First broker login did not run the role config, or the login used a client without `fullScopeAllowed` |
| `sub` changes between logins | Google IdP `syncMode` is not `IMPORT` |
| Admin API `401` | `gateway-admin` secret disagrees with `${IDP_ADMIN_SECRET}` in the environment |
| Admin API `403` | A realm-management role was removed from the `gateway-admin` service account |
| Users missing from `/admin/users` | More than 200 accounts. The contract stops at 200; the list is not paginated |
| Iframe polling times out in the browser | `X-Frame-Options: DENY` on the `id.` host. It must be `SAMEORIGIN` ([ADR-0008](../adrs/8-idp-host-frame-self.md)) |
