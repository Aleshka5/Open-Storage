> **ID:** US-06
> **Status:** TODO
> **Specs:** [identity v1](../../auth-gateway/external-contracts/identity-v1.md), [idp roles](../../auth-gateway/idp/init.md), [gateway API contract](../../auth-gateway/gateway/api-contract.md), [US-05](../us-05-storage-namespace/init.md)

## Overview

The app reads identity v1 instead of the legacy header set. Today `get_current_user` reads `X-User-Id`, falls back to `X-Auth-User-Id`, prefers `X-Storage-Role`, and making an HTTP call to User-Service (`USER_SERVICE_URL`) when the role header is absent. The gateway strips all of those names and sends `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Roles` and `X-Auth-Session`. The app's four-value storage role survives as a projection of `X-Auth-Roles`; the directory lookup goes.

Tasks: [header reader](tasks/task-01-header-reader.md), [role projection](tasks/task-02-role-projection.md), [remove User-Service](tasks/task-03-remove-user-service.md), [vault session key](tasks/task-04-vault-session.md), [error envelope](tasks/task-05-error-envelope.md), [v1-only regression](tasks/task-06-v1-regression.md), [admin routes](tasks/task-07-admin-routes.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The app trusts the v1 headers and does not verify the bearer JWT. It is reachable only on `open_network`, which is the header-trust condition [identity-v1.md](../../auth-gateway/external-contracts/identity-v1.md) sets. | Verifying RS256 against the realm JWKS, which buys nothing while the app has no public port and costs a JWKS cache and a failure mode |
| D2 | The user key is `X-Auth-Subject`. The app does not invent a value when it is absent: no subject is 401. The column type is a migration question, not a header-reader question; [US-08](../us-08-data-cutover/init.md) settles what `users.id` holds after the cutover. | Parsing the header into a UUID in the reader, which would reject a subject the idp may issue in another string form |
| D3 | `Role` keeps its four values. The gates stay where they are: `check_role(Role.FAMILY, Role.ADMIN)` on shared and resume routes, `check_role(Role.ADMIN)` on `/api/admin`. `Role` is computed from `X-Auth-Roles`: `svc:storage:blocked` → `BLOCKED`; else `svc:storage:admin` → `ADMIN`; else `svc:storage:family` → `FAMILY`; else `STRANGER`. Blocked wins over any grant. `Role.can_access_shared()` and `Role.can_access_admin()` have no caller today and are deleted rather than kept as a second gate. | Deleting `Role` and branching on realm role strings across the routers |
| D4 | A missing or empty `X-Auth-Roles` is `STRANGER`, not an error. No role means stranger ([idp roles](../../auth-gateway/idp/init.md)). | Treating an absent header as misconfiguration, which would 500 every signed-in user who has no storage grant |
| D5 | A malformed header stays fail-closed: a token that is not a known `svc:storage:*` value is ignored, and an absent `X-Auth-Subject` with a valid session answers 401. The app never invents a role from a role it cannot parse. | Falling back to a directory or a default role on a malformed value |
| D6 | The User-Service client, its port, its settings and its cache are removed. No HTTP identity call leaves the app. | Keeping User-Service as a fallback when the header is missing |
| D7 | The encrypted vault's session key is derived in-process from the `__Secure-open_session` cookie, which the gateway mints with `Domain=.filenkov.store`. The `auth_session` cookie and `AUTH_COOKIE_NAME` are removed. | Reading `auth_session`, a cookie the old auth service minted and the new gateway never sets |
| D8 | A second login is a new vault session. The key follows the new session cookie, so the vault locks on the new session and the old Redis key expires on its TTL. This replaces today's behaviour, where one `auth_session` survived a re-login. | Carrying the vault key across logins by keying it on the user, which would let a second device open the first device's vault |
| D9 | The app keeps its own error envelope for its own errors. The gateway owns the edge errors. The app does not answer `{"error": "..."}` and does not remap the gateway's. | Conforming the app's errors to the edge's one-string envelope |
| D10 | The app's own admin check stays the authority for `/api/admin/**`. The gateway allows `service(storage, family, admin)` on everything but `/health`, and `check_role(Role.ADMIN)` answers 403 for a family member reaching an admin route. | Moving admin enforcement to the gateway with a `policy: admin` route, which would deny a `svc:storage:admin` who is not a realm `admin` |

## Goals

- One header reader produces the principal, and only v1 names feed it.
- The storage role is a pure function of `X-Auth-Roles` with a test per combination.
- The app makes no identity HTTP call.
- The vault performs an unlock and a read under the new session cookie.

## Non-goals

- The user projection's match rule. Moving `users.id` onto the new subject is data work ([US-08](../us-08-data-cutover/init.md)).
- RAG indexing.
- The gateway config, the proxy and DNS. Those are [US-07](../us-07-edge-host/init.md).
- A JWT verifier. See D1.

## User Story

**As** a signed-in family member, I want the storage app to read the identity the gateway sends, so that my files, photos and vault work on `storage.filenkov.store` with one login and no directory service.

**Acceptance**

- `grep -rn "X-User-Id\|X-Storage-Role\|X-Auth-User-Id\|USER_SERVICE_URL\|auth_session" src/open-storage` finds nothing but tests asserting they are ignored or absent.
- `grep -rn "user_service" src/open-storage/app --include='*.py'` is empty.
- A GET to `/api/files` carrying only `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Roles: svc:storage:family` answers 200 and the same rows as the legacy stack for that user.
- A table test maps `X-Auth-Roles` to `Role`: `` → `STRANGER`, `svc:storage:family` → `FAMILY`, `svc:storage:admin` → `ADMIN`, `svc:storage:family svc:storage:admin` → `ADMIN`, `svc:storage:blocked svc:storage:admin` → `BLOCKED`, `svc:image:family` → `STRANGER`.
- A `STRANGER` gets 403 on `/api/shared/**` and a `FAMILY` gets 200; a `BLOCKED` gets 403 on every route.
- A request with no `X-Auth-Subject` answers 401 and creates no `users` row.
- `POST /api/private/unlock` with the passphrase succeeds under a `__Secure-open_session` cookie, a read of a private file succeeds with the same cookie, and the same read fails after a second login minted a new session cookie.
- `podman logs open-storage-app | grep -c "User-Service"` is 0 after a browse of each section.

## Definition of Done

- [ ] `pytest` passes, including the v1-only regression and the vault session test.
- [ ] The acceptance items above hold on the stand through the gateway.
- [ ] The app's error envelope is unchanged for its own errors, and a 401 from the edge passes through untouched.
- [ ] `docs/auth-gateway/external-contracts/identity-v1.md` lists this app as a v1 consumer without restating its internals.
