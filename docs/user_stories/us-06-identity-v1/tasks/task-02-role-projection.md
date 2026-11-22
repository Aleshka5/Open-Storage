# task-02 Role projection

Story: [US-06](../init.md)

## Outcome

One pure function turns `X-Auth-Roles` into `Role`, and `Role` keeps its four values. Nothing else computes a role.

## Paths

- `src/open-storage/app/app/domain/value_objects/role.py`
- `src/open-storage/app/tests/` — the projection table test

## Done when

A table test covers, for the header value: `` → `STRANGER`; `svc:storage:family` → `FAMILY`; `svc:storage:admin` → `ADMIN`; `svc:storage:family svc:storage:admin` → `ADMIN` (either order); `svc:storage:blocked svc:storage:admin` → `BLOCKED`; `svc:storage:blocked svc:storage:family` → `BLOCKED`; `svc:image:family` → `STRANGER`; `svc:storage` and `storage:family` → `STRANGER`. `can_access_shared()` and `can_access_admin()` are gone, and no router changes: `check_role` keeps its signature. The precedence is most-restrictive-first, the same order the gateway's own `ServiceLevel` uses.
