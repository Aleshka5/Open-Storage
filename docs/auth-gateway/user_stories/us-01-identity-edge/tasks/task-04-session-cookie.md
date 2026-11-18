# task-04 Session cookie

Story: [US-01](../init.md)

## Outcome

AES-256-GCM seal and open. Three cookies from the gateway message contract. One refresh in flight per `sub`.

## Paths

- `src/auth-gateway/gateway/internal/session/`

## Done when

Tests cover a forged cookie, an expired session, `invalid_grant` clearing cookies, and two parallel refreshes producing one token exchange and two valid responses.
