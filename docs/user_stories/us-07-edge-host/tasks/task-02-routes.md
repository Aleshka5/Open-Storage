# task-02 Route set

Story: [US-07](../init.md)

## Outcome

The host's routes are `/health` public and `/**` at `service(storage, family, admin)`, and the edge answers the identity-v1 error bodies for each refusal.

## Paths

- `src/auth-gateway/gateway/config.yaml` — the host's `routes:`
- `src/auth-gateway/gateway/internal/policy/` — reads the compiled policy

## Done when

`/health` is reachable anonymously; a stranger gets `403 {"error":"forbidden"}`, not a redirect; `svc:storage:blocked` gets `403 {"error":"blocked"}`; a family account gets through to the app; the `service:` key on the host makes `blocked` beat the route policy, which is the gateway's `policy.Blocked` behaviour, not a second rule in the app.
