# task-06 Edge proxy

Story: [US-01](../init.md)

## Outcome

Host, path, and method match. Inbound `X-Auth-*`, `X-User-Id`, and `X-Storage-Role` are stripped. The canonical identity headers and `X-Forwarded-*` are injected. Reverse proxy uses per-host timeouts, WebSocket upgrade, JSON errors, an access log, and `/healthz`, `/readyz`, `/metrics`.

## Paths

- `src/auth-gateway/gateway/internal/edge/`

## Done when

Tests against an `httptest` upstream show client identity headers removed, `101` passed through, SSE not buffered, a host timeout returning `504`, `deny` returning `404`, and `401` versus `302` chosen from `Accept`, `X-Requested-With`, and the `/api/` prefix. The runtime invariants in the gateway external contract hold.
