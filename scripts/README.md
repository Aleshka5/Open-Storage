# scripts

Checks and setup for the auth-gateway stand. The bootstrap scripts of the edge stand (US-01, removed; the scripts are their own owner now).

| Script | What it does | Writes |
|---|---|---|
| `grant-admin.sh <email>` | Grants realm role `admin` through the Keycloak Admin API. Exit `2` when no user has that email, `0` when the role is already there. | Keycloak only |
| `verify-edge.sh` | One anonymous request per SSO host, through the proxy and straight to the gateway. `AUTH_COOKIE_SIGNED_IN` / `AUTH_COOKIE_ADMIN` add signed-in and admin rows; without them those rows say `SKIP`. | Nothing, GET only |
| `golden.sh` | `verify-edge.sh`, plus `/healthz`, `/readyz`, and `caddy validate`. This is the stand check for `make verify`. | Nothing, GET only |
| `verify-storage-host.sh` | Curls `BASE_URL` for storage `/health` and anonymous `/api/files`, plus family, admin, stranger, and blocked when those cookies are set. Prints each status and body. Exit `2` when a probe was not run, including the download past 60s unless `DOWNLOAD_URL` is set. | Nothing, GET only |

Requirements: `bash` 4+, `curl`, `jq`; `caddy` only for the last step of `golden.sh`. `grant-admin.sh` takes `IDP_ADMIN_SECRET` from the environment first, then `deploy/auth-gateway/.env`; it never prints it.

Variables the scripts read: `KEYCLOAK_URL`, `REALM`, `IDP_ADMIN_CLIENT_ID`, `IDP_ADMIN_SECRET`, `ENV_FILE` (grant-admin); `GATEWAY_ADDR`, `PROXY_SCHEME`, `AUTH_COOKIE_*`, `TLS_VERIFY`, `GATEWAY_CONFIG` (verify-edge, golden); `CADDYFILE` (golden).

Open-storage cutover plans (no live dump or mirror): [open-storage-cutover](open-storage-cutover/) and [cutover.md](../docs/open-storage/cutover.md).

`engine.mk` picks `podman` or `docker`. `images.mk` is `make release` and `make up`'s pull. Both are included from `deploy/<namespace>/Makefile`. The procedure is [images.md](../docs/images.md).
