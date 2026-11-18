# task-03 OIDC verifier

Story: [US-01](../init.md)

## Outcome

Discovery, JWKS cache by `kid` (TTL 15m), and `Verify(access) → Identity{Subject, Email, Name, Roles, SID}` with checks of `iss`, `aud`, `exp`, and `typ`.

## Paths

- `src/auth-gateway/gateway/internal/oidc/`

## Done when

Tests against a fake JWKS cover a valid token, a bad signature, a foreign `aud`, an expired `exp`, and an unknown `kid` that reloads keys exactly once.
