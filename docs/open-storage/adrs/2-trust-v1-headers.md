## Status

Accepted

## Decision

The open-storage app trusts identity v1 headers and does not verify the bearer JWT. It is a v1 consumer reachable only on `open_network`, which is the header-trust condition in [identity v1](../../auth-gateway/external-contracts/identity-v1.md).

`get_current_user` reads `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Roles` and `X-Auth-Session`. An absent subject is 401 and writes no `users` row. The subject is not parsed into a UUID in the reader. `users.id` stays a UUID column; what that column holds after cutover is [US-08](../../user_stories/us-08-data-cutover/init.md).

`Role` stays `STRANGER`, `FAMILY`, `ADMIN`, `BLOCKED`. It is a pure function of `X-Auth-Roles`: `svc:storage:blocked` wins, else `svc:storage:admin`, else `svc:storage:family`, else `STRANGER`. A missing or empty header is `STRANGER`. Unknown tokens are ignored. `check_role` keeps its signature. `Role.can_access_shared()` and `Role.can_access_admin()` are removed.

The User-Service client, port, settings and cache are removed. No identity HTTP call leaves the app. The admin user list is the local `users` table.

The vault session key is the SHA-256 hex of the `__Secure-open_session` cookie, used as the Redis key. `auth_session` and `AUTH_COOKIE_NAME` are removed. A missing cookie is 401. Two logins are two keys. `unlock_attempts` stays keyed on user and IP.

The app keeps `{"detail": {"error_code", "message"}}` for errors it produces. It does not remap a gateway body `{"error": "..."}`.

`/api/admin/**` stays the app's `check_role(Role.ADMIN)` gate. The gateway allows `service(storage, family, admin)` on that path, so a family member who passes the gateway is denied here with the app 403 envelope. That double check is intended: a gateway `policy: admin` route would deny `svc:storage:admin` without realm `admin`.

## Rejected

Verifying RS256 against the realm JWKS. Parsing `X-Auth-Subject` into a UUID in the reader. Deleting `Role` and branching on realm role strings. Treating a missing `X-Auth-Roles` as a 500. Keeping User-Service as a fallback. Reading `auth_session`. Keying the vault on the user so a second device opens the first vault. Conforming app errors to the edge envelope `{"error": "..."}`. Moving `/api/admin/**` to a gateway `policy: admin` route.

## Cost

The app no longer learns another user's storage role from a directory. The `users` table has no role column, so the admin list reports the local projection (role `STRANGER` until a later change stores a grant). A subject that is not a UUID string cannot be inserted while `users.id` is a UUID column; the projection writes no row. Operators drop `USER_SERVICE_*` and `AUTH_COOKIE_NAME` from the app environment. `deploy/open-storage/.env.example` is outside this change.

## Risk

Header trust holds only while the app has no public port. A client that can reach `app:8000` on `open_network` can forge the five headers. A non-UUID subject fails closed at the column until US-08. A family member who is allowed through the gateway still receives the app's 403 on `/api/admin/**`, which is a different body from the edge's `{"error":"forbidden"}`.
