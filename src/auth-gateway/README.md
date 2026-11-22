# src/auth-gateway

Code for the auth-gateway namespace.

| Piece | Where | Docs |
|---|---|---|
| gateway | `gateway/` | [init](../../docs/auth-gateway/gateway/init.md), [API contract](../../docs/auth-gateway/gateway/api-contract.md), [external contract](../../docs/auth-gateway/gateway/external-contracts.md) |
| idp | `idp/realm.json`, `idp/theme/` | [init](../../docs/auth-gateway/idp/init.md), [API contract](../../docs/auth-gateway/idp/api-contract.md), [external contract](../../docs/auth-gateway/idp/external-contract.md) |
| resume-page | `resume-page/` | [design](../../docs/auth-gateway/frontend/design.md) |
| proxy | not here — [Caddyfile](../../deploy/auth-gateway/Caddyfile) | [init](../../docs/auth-gateway/proxy/init.md), [external contract](../../docs/auth-gateway/proxy/external-contract.md) |

`idp_db` is the Postgres image in compose. It has no source tree. See the idp [external contract](../../docs/auth-gateway/idp/external-contract.md).

Gateway tests sit next to the packages they lock (`*_test.go`). Resume-page tests sit next to the components (`*.test.tsx`). `idp/tests/` is empty.
