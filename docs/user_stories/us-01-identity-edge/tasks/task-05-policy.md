# task-05 Policy

Story: [US-01](../init.md)

## Outcome

`public | session | admin | deny | service(svc[, level…])` returns allow or deny for an `Identity`.

## Paths

- `src/auth-gateway/gateway/internal/policy/`

## Done when

A role × policy table covers stranger, family, admin, and blocked, including `service(storage, admin)` without `family`, and `deny` for every role.
