# task-03 Remove User-Service

Story: [US-06](../init.md)

## Outcome

The User-Service client, its port, its settings and its cache leave the app. No identity HTTP call remains.

## Paths

- `src/open-storage/app/app/infrastructure/user_service/` — deleted
- `src/open-storage/app/app/application/ports/user_directory.py` — deleted
- `src/open-storage/app/config.py` — `UserServiceSettings` deleted
- `deploy/open-storage/.env.example` — `USER_SERVICE_*` deleted
- `src/open-storage/app/tests/test_user_service_client_cache.py` — deleted

## Done when

The app starts with no `USER_SERVICE_URL` in the environment; `grep -rn "user_service\|UserService" src/open-storage/app --include='*.py'` is empty; the admin user list no longer claims a directory as its source (see [task-07](task-07-admin-routes.md)); `pytest` passes.
