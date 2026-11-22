# task-03 Env and Makefile

Story: [US-05](../init.md)

## Outcome

`deploy/open-storage/.env.example` names every variable the app reads, with no literal secret, and a `Makefile` carries the lifecycle targets the other namespaces use.

## Paths

- `deploy/open-storage/.env.example`
- `deploy/open-storage/Makefile`

## Done when

Every `validation_alias` in the app's settings appears in `.env.example`; the identity-era variables `USER_SERVICE_URL`, `USER_SERVICE_TIMEOUT_MS`, `USER_SERVICE_CACHE_TTL_SECONDS` and `AUTH_COOKIE_NAME` are gone (see [US-06 task 03](../../us-06-identity-v1/tasks/task-03-remove-user-service.md)); `make up`, `make down`, `make doctor` are defined; `doctor` fails when a required variable is missing rather than starting partly configured.
