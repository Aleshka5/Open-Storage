# task-01 Header reader

Story: [US-06](../init.md)

## Outcome

`get_current_user` builds the principal from `X-Auth-Subject`, `X-Auth-Email`, `X-Auth-Name` and `X-Auth-Roles`. The legacy names are not read at all.

## Paths

- `src/open-storage/app/app/presentation/dependencies/auth.py`

## Done when

The reader names the five v1 headers ([identity v1](../../../auth-gateway/external-contracts/identity-v1.md)) and nothing else; an absent `X-Auth-Subject` answers 401 and writes no `users` row; a request that carries only `X-User-Id` and `X-Storage-Role` answers 401; `get_user_repository`, `get_quota_repository` and the projection call are unchanged in behaviour.
