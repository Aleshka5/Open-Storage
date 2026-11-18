# idp — message contract

Keycloak 26.8.2 is the only identity source. It does not know hosts, routes, or which applications exist.

Public URL: `https://id.filenkov.store`. Issuer: `https://id.filenkov.store/realms/filenkov`. JWKS: `/realms/filenkov/protocol/openid-connect/certs`. Tokens are RS256.

Claims that are read: `sub`, `email`, `name`, `preferred_username`, `realm_access.roles`, `sid`, `exp`, `aud`.

## Realm

| Object | Value |
|---|---|
| Realm | `filenkov`. One realm for every host. |
| Login | Google IdP, `syncMode: IMPORT`, `kc_idp_hint=google`. The Keycloak form is not shown. |
| First broker login | Create the user if unique. Confirm-link is off. |
| Registration | Off. Google login is the only way to create a user. |
| Username | `registrationEmailAsUsername: true` — the console label is "Email as username". Keycloak 26 has no `emailAsUsername` realm field; an import that carries one is refused |
| Duplicate emails | Forbidden |
| Client `gateway` | Confidential, standard flow, PKCE S256, redirect `https://filenkov.store/auth/callback` |
| Client `gateway-admin` | Confidential service account. Roles `view-users`, `manage-users`, `query-users`, `view-realm`. |
| Client `account` | Off |
| Client `gateway` audience | An audience mapper adds `account` to the access token. Without it a token with no client roles carries no `aud` at all, and the edge rejects it ([gateway external contract](../../gateway/External-contract.md)) |
| Theme | `filenkov` |

`realm.json` is the only realm configuration. Admin Console edits are not allowed: they die with the volume and drift from git. Users live in the database and are not in git.

## Lifetimes

| Item | Value |
|---|---|
| Access token | 5 minutes. It cannot be revoked. |
| SSO session idle | 7 days |
| SSO session max | 30 days, then Google login again |
| Refresh | Rotation on. `revokeRefreshToken: true`. A stolen refresh survives one exchange. |

Logout of every session: `POST /admin/realms/filenkov/users/{id}/logout`, plus not-before on the user. There is no revocation list.

Brute force: `bruteForceProtected: true`, `failureFactor: 5`, `waitIncrementSeconds: 60`.

Ready probe: `https://id.filenkov.store/realms/filenkov/health/ready` (public on the id host).

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

Who may change roles is enforced by gateway, not by Keycloak. See the gateway [message contract](../../gateway/API/Message-contract.md).

Adding a service with roles, in one change:

1. Gateway `services:` and a host block.
2. Realm roles `svc:<name>:admin`, `:family`, `:blocked`.
3. Proxy site block.
4. DNS.

## Bootstrap

Keycloak has no "first user is admin" counter. After the first Google login, `scripts/grant-admin.sh <email>` grants realm role `admin`. The script reads `gateway-admin` from the env file and does not print the password.

`realm.json` carries no secret: it names `${GOOGLE_CLIENT_ID}`, `${GOOGLE_CLIENT_SECRET}`, `${IDP_CLIENT_SECRET}` and `${IDP_ADMIN_SECRET}` as placeholders, and Keycloak substitutes them from the environment during `--import-realm`.

`KC_BOOTSTRAP_ADMIN_*` applies only to an empty database. Remove it from the env file after the first start. Console recovery stays at `https://id.filenkov.store/admin/` inside idp, so it still works when gateway policy is wrong, as long as `idp_db` is alive.
