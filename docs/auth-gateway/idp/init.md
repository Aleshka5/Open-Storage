# idp — init

What the identity provider in this namespace is, how it runs, and the facts a caller or an operator starts from. API surface is in [api-contract.md](api-contract.md); the process and its Google and Postgres wiring are in the [external contract](external-contract.md).

## Purpose

Keycloak 26.8.2 is the only identity source. It owns who a user is and which services they may use: accounts, roles, sessions, signing keys, tokens. It does not know hosts, routes, or which applications exist — that is the gateway.

One realm, `filenkov`, for every host. Google is the only login; the Keycloak username form is never shown. Registration is off, so a Google login is the only way an account appears.

| Fact | Value |
|---|---|
| Image | `quay.io/keycloak/keycloak:26.8.2`, pinned ([external contract](external-contract.md)) |
| Realm | `filenkov`, imported from `src/auth-gateway/idp/realm.json` |
| Public URL | `https://id.filenkov.store` |
| Issuer | `https://id.filenkov.store/realms/filenkov` |
| Database | `idp_db`, Postgres 17, database and user `keycloak` |
| Theme | `filenkov`, mounted read-only |
| Token signing | RS256, keys in `idp_db` |
| Container port | `8080` (HTTP; TLS ends at the proxy) |
| Compose | `deploy/auth-gateway/docker-compose.yaml`, service `idp` and `idp_db`, network `open_network` |

It reaches nothing outward except Google. The gateway reaches it on `open_network` at `http://idp:8080` and the browser reaches it through the edge at `https://id.filenkov.store`; the second call is what sets `KC_HOSTNAME`, so the issuer in every answer is the public one.

## Realm

| Object | Value |
|---|---|
| Login | Google IdP `google`, `syncMode: IMPORT`, `kc_idp_hint=google` |
| First broker login | Create the user if unique. Confirm-link is off. |
| Registration | Off |
| Username | `registrationEmailAsUsername: true` — the console label is "Email as username". Keycloak 26 has no `emailAsUsername` realm field; an import that carries one is refused |
| Duplicate emails | Forbidden |
| Client `gateway` | Confidential, standard flow, PKCE S256, redirects `https://filenkov.store/auth/callback` and `https://mvp.filenkov.store/auth/callback` |
| Client `gateway-admin` | Confidential service account. Realm-management roles `view-users`, `manage-users`, `query-users`, `view-realm`. |
| Client `account` | Off |
| `gateway` audience | An audience mapper adds `account` to the access token. Without it a token with no client roles carries no `aud` at all, and the edge rejects it ([gateway external contract](../gateway/external-contracts.md)) |
| Theme | `filenkov` |

`realm.json` is the only realm configuration. Admin Console edits are not allowed: they die with the volume and drift from git. Users live in the database and are not in git.

Two things the file carries beyond the table: the first-broker-login and user-link flows are realm copies suffixed `filenkov`, so changing the stock flow of the image does not change this realm; and the only user in git is the `gateway-admin` service account.

## Lifetimes

| Item | Value |
|---|---|
| Access token | 5 minutes. It cannot be revoked. |
| SSO session idle | 7 days |
| SSO session max | 30 days, then Google login again |
| Refresh | Rotation on. `revokeRefreshToken: true`, `refreshTokenMaxReuse: 0`. A stolen refresh survives one exchange. |

Logout of every session: `POST /admin/realms/filenkov/users/{id}/logout`, plus not-before on the user. There is no revocation list; an access token lives out its five minutes.

Brute force: `bruteForceProtected: true`, `failureFactor: 5`, `waitIncrementSeconds: 60`.

Readiness is not a probe URL on this host today; see the [API contract](api-contract.md#health) before writing one.

## Roles

One mechanism: realm roles. No groups, no client roles, no attributes used for authorization.

| Role | Who | Effect |
|---|---|---|
| `admin` | Operator | `/admin`, hosts with `policy: admin`, Keycloak console |
| `svc:<service>:admin` | Service owner | Full use of that service, and may edit its roles |
| `svc:<service>:family` | Family | Ordinary use of that service |
| `svc:<service>:blocked` | — | That service is closed. The account stays enabled. |

`<service>` is a key of gateway `services:`: `storage`, `image`, `rag`, `audio`.

No role means stranger. There is no `stranger` role. There is no global `family` role. Global block is `user.enabled = false`, plus logout, not a role. `blocked` on one service is not a global block.

Role graph is not used. Policy treats `admin` of a service as including `family`.

Who may change roles is enforced by gateway, not by Keycloak. See the gateway [API contract](../gateway/API/api-contract.md).

Adding a service with roles, in one change:

1. Gateway `services:` and a host block.
2. Realm roles `svc:<name>:admin`, `:family`, `:blocked`.
3. Proxy site block.
4. DNS.

## Bootstrap

Keycloak has no "first user is admin" counter. After the first Google login, `scripts/grant-admin.sh <email>` grants realm role `admin`. The script reads `gateway-admin` from the env file and does not print the password.

`realm.json` carries no secret: it names `${GOOGLE_CLIENT_ID}`, `${GOOGLE_CLIENT_SECRET}`, `${IDP_CLIENT_SECRET}` and `${IDP_ADMIN_SECRET}` as placeholders, and Keycloak substitutes them from the environment during `--import-realm`.

`KC_BOOTSTRAP_ADMIN_*` applies only to an empty database. Remove it from the env file after the first start. Console recovery stays at `https://id.filenkov.store/admin/` inside idp, so it still works when gateway policy is wrong, as long as `idp_db` is alive.

There is no readiness probe on the host, so "the first start takes about 60 seconds" is the wait: an empty database builds the server, then imports the realm.

## Drift

The only check that matters: export the live realm, drop `users`, `components`, and `id`, and diff against git. Anything else in the diff is an edit made outside git. Restore is a dump into an empty volume, then start without `--import-realm` ([external contract](external-contract.md)).
