# task-07 Admin routes

Story: [US-06](../init.md)

## Outcome

`/api/admin/**` keeps the app's own `check_role(Role.ADMIN)` gate. The gateway allows `service(storage, family, admin)` on that path, so the app is the authority for admin pages, and the app records that position.

## Paths

- `src/open-storage/app/app/presentation/middleware/check_role.py`
- `src/open-storage/app/app/presentation/routers/admin_router.py`
- `src/open-storage/app/app/presentation/routers/indexing_router.py`

## Done when

A `FAMILY` request to each `/api/admin/*` route answers the app's 403 envelope, not the gateway's; a `svc:storage:admin` request answers 200 whether or not the realm `admin` is present; the admin user list is served from the local `users` table, because the directory is gone; the double check (gateway allows, app denies) is stated as intended, with the reason that a `policy: admin` route would deny a service admin who is not a realm admin.
