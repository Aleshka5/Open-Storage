# task-06 Switch users

Story: [US-08](../init.md)

## Outcome

The host stops taking the old path and the family is told the one new thing they have to do: log in again.

## Paths

- The old edge config (`Auth-Service/deploy/Caddyfile.filenkov`) — the storage site block is removed
- `deploy/auth-gateway/Caddyfile` — already carries the name ([US-07 task 04](../../us-07-edge-host/tasks/task-04-proxy.md))

## Done when

The old stack is stopped with its volumes intact; the old edge no longer serves `storage.filenkov.store`; the new host answers a family login; the subject mapping from [D7](../init.md) is applied so the first login lands on the existing `users` row, and a probe confirms no new `users` row is created; the rollback is written and tested once on a stand.
