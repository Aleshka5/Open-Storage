# frontend — security

The page does not hold tokens, does not read the session cookie, and does not know secrets. The theme cookie is a UI preference, not a credential ([brand book §1](../../brand-book/init.md)).

- Calls are same-origin, `credentials: "include"`. The client strips `Authorization`, `X-User-Id`, and every `X-Auth-*` header before send.
- A gateway `401 {"error":"unauthorized"}` sends the browser to the hub sign-in URL. The page does not start OAuth and does not store a token.
- A gateway `403 {"error":"blocked"}`, or a RAG body whose error code is `forbidden`, shows access denied and does not retry.
- A RAG `401` envelope is not the gateway redirect. The page leaves it to the screen that made the call.
- Hiding a control is not enforcement. The gateway and the RAG services decide.

`GET /auth/session` is apex-only ([gateway API contract](../../auth-gateway/gateway/api-contract.md)). This host has no equivalent of storage’s `GET /api/auth/me`, so the header does not show an account name.
