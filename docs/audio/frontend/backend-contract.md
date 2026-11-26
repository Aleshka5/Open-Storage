# audio frontend — backend contract

Calls stay on this host. The browser sends the gateway cookie (`credentials: 'include'`) and no `Authorization` header. Identity headers are the gateway's, owned by [identity v1](../../auth-gateway/external-contracts/identity-v1.md).

The gate is `GET /api/me` on audio-api, not `GET /auth/session`. Session is apex-only ([gateway API contract](../../auth-gateway/gateway/api-contract.md)). `GET /api/me` answers the voice record, not the account email or name, so the header shows “Signed in” rather than an address.

Every other call is under `/api` on the same origin: recordings, phrases, audio bytes, voice notes, nicks. The dev server proxies `/api` to `API_PROXY_TARGET`. Production leaves `VITE_API_BASE_URL` empty, so the paths stay relative.

`GET /api/me` does not include `X-Auth-Email` or `X-Auth-Name`. Showing the account the way storage’s `GET /api/auth/me` does needs that body, and this page does not invent it.
