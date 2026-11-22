# scripts

Checks and setup for the auth-gateway stand. Spec: [US-01 task 10](../docs/user_stories/us-01-identity-edge/tasks/task-10-bootstrap-scripts.md).

| Script | What it does | Writes |
|---|---|---|
| `grant-admin.sh <email>` | Grants realm role `admin` through the Keycloak Admin API. Exit `2` when no user has that email, `0` when the role is already there. | Keycloak only |
| `verify-edge.sh` | One anonymous request per SSO host, through the proxy and straight to the gateway. `AUTH_COOKIE_SIGNED_IN` / `AUTH_COOKIE_ADMIN` add signed-in and admin rows; without them those rows say `SKIP`. | Nothing, GET only |
| `golden.sh` | `verify-edge.sh`, plus `/healthz`, `/readyz`, and `caddy validate`. This is the stand check for `make verify`. | Nothing, GET only |

Requirements: `bash` 4+, `curl`, `jq`; `caddy` only for the last step of `golden.sh`. `grant-admin.sh` takes `IDP_ADMIN_SECRET` from the environment first, then `deploy/auth-gateway/.env`; it never prints it.

Variables the scripts read: `KEYCLOAK_URL`, `REALM`, `IDP_ADMIN_CLIENT_ID`, `IDP_ADMIN_SECRET`, `ENV_FILE` (grant-admin); `GATEWAY_ADDR`, `PROXY_SCHEME`, `AUTH_COOKIE_*`, `TLS_VERIFY`, `GATEWAY_CONFIG` (verify-edge, golden); `CADDYFILE` (golden).

Open-storage cutover plans (no live dump or mirror): [open-storage-cutover](open-storage-cutover/) and [cutover.md](../docs/open-storage/cutover.md).
