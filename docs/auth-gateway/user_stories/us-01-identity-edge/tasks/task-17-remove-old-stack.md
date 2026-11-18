# task-17 Remove the old stack

Story: [US-01](../init.md)

## Outcome

Seven days after cutover, remove the old auth service, user service, and hermes auth gateway, including volumes, and drop DNS names and site blocks that no longer exist.

## Done when

A search of project sources for `auth_access`, `auth_refresh`, `auth_session`, and `X-User-Id` is empty, apart from history kept in docs.
