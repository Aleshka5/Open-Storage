# task-10 Bootstrap scripts

Story: [US-01](../init.md)

## Outcome

`scripts/grant-admin.sh <email>` grants realm role `admin` through the Admin API. The password comes from the env file and is never printed.

`scripts/verify-edge.sh` sends one request per SSO host through the proxy and one directly to the gateway.

`scripts/golden.sh` is the stand check used by `make verify`.

## Done when

`shellcheck scripts/*.sh` passes. The scripts run against a built stand.
