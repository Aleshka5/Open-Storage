# task-06 Roles

Story: [US-07](../init.md)

## Outcome

The three storage roles exist in the realm and are the only names the app projects. Nothing is added, because `realm.json` already carries them.

## Paths

- `src/auth-gateway/idp/realm.json`

## Done when

`svc:storage:admin`, `svc:storage:family` and `svc:storage:blocked` are in `realm.json` and in the live realm, and `storage` is in the gateway's `services:` so every `svc:storage:*` name is admitted by config validation; the realm export diff shows no other change; the operator's account is checked against the projection in [US-06 task 02](../../us-06-identity-v1/tasks/task-02-role-projection.md).
