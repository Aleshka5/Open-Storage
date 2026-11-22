# task-07 BFF

Story: [US-01](../init.md)

## Outcome

`/auth/login`, `/auth/callback`, `/auth/logout`, and `/auth/session` match the gateway message contract, including the `return_to` allowlist, one-time `state`, `nonce`, PKCE S256, and the `Origin` check on logout.

## Paths

- `src/auth-gateway/gateway/internal/bff/`

## Done when

Tests cover an invalid `return_to` falling back to `public_origin`, a foreign `state` returning `302` with `auth_error`, a mismatched `nonce` rejected, and logout without `Origin` returning `403`.
