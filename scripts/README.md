# scripts

Checks and setup for the whole repository. Nothing is implemented yet.

Planned for auth-gateway:

| Script | Purpose |
|---|---|
| `grant-admin.sh` | Grant realm role `admin` to an email. Password stays in the env file. |
| `verify-edge.sh` | One request per SSO host, through the proxy and directly to the gateway. |
| `golden.sh` | Stand check used by `make verify`. |

Spec: [US-01 task 10](../docs/auth-gateway/user_stories/us-01-identity-edge/tasks/task-10-bootstrap-scripts.md).
