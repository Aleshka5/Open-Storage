# task-14 Consumers on v1

Story: [US-01](../init.md)

## Outcome

Each consumer reads identity v1. This work is outside this repository, one change per project, and it lands before cutover.

| Project | Change |
|---|---|
| WebStorage | `X-User-Id` / `X-Storage-Role` → `X-Auth-Subject` / `X-Auth-Roles`. Vault key follows `X-Auth-Session` instead of an `auth_session` cookie. |
| RAG-Chat | `X-Auth-User-Id` → `X-Auth-Subject`. `X-Auth-Role` → parse `X-Auth-Roles`. |
| ASR-Service | `X-Auth-User-Id` → `X-Auth-Subject` |
| qwen-image-service | `X-Auth-User-Id` / `Name` / `Email` → the v1 names |
| Switch-Service | No change. The edge injects `X-Service-Token`. |
| hermes-auth-gateway | Retire. `hermes.filenkov.store` bypasses SSO. |

## Done when

Each project has a test that reads the new headers. A search for `X-User-Id`, `X-Storage-Role`, and `X-Auth-User-Id` is empty. One real operation works under the operator account: a file upload, a RAG question, an ASR transcript, an image generation.
