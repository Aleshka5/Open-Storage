# task-08 Admin API

Story: [US-01](../init.md)

## Outcome

`/admin/users`, role grant per service, `PATCH` enabled, and `PUT …/admin`, including last-admin and service-admin checks.

Close the error-envelope conflict in [init.md](../../../init.md) in this task: one body shape for edge and admin, updated in the contracts.

## Paths

- `src/auth-gateway/gateway/internal/adminapi/`

## Done when

Tests against a fake Keycloak Admin API cover `409 {"error":"last_admin"}`, a foreign service returning `403`, `svc=admin` on the service path returning `400`, and `level: null` removing the role.
