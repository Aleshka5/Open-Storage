# Identity contract v1

One version. No legacy mode, no second set of names, no version negotiated by header. Changing this contract means updating every consumer in the same release.

Owned here because product applications live outside the namespace. Gateway is the only writer.

## Headers an application receives

| Header | Value |
|---|---|
| `Authorization` | `Bearer <access JWT>`. The cookie value, not a new token. |
| `X-Auth-Subject` | `sub`. Stable user id in idp. Use it as a foreign key. |
| `X-Auth-Email` | `email` |
| `X-Auth-Name` | `name` |
| `X-Auth-Roles` | Realm roles, space-separated, sorted. Omitted when empty, not sent as an empty string. |
| `X-Auth-Session` | `sid`. Session id, not a user id. Two logins of one person are two `sid` values. Data tied to `sid` dies when idp kills the session. No callback. |
| `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-For` | Set by proxy, rewritten by gateway |

Before injection, these are removed with no exception: any `X-Auth-*` (any case), `X-User-Id`, `X-Storage-Role`, `X-Original-User`, and `Authorization`.

An application never receives an identity header that the client sent. `Authorization` is on that list because it is an identity header: the value an application sees is the one the gateway injected, or nothing at all on a `public` route.

`X-Forwarded-For` is the caller as the proxy in front of the gateway saw it: the last hop of the header, not the first, because the part a client can write comes before it.

## How an application checks

Trust the headers only when the application is reachable solely on `open_network`.

Otherwise verify the bearer JWT: RS256 against the realm JWKS, `iss` equals the realm issuer, `aud` contains `account`, `azp` equals `gateway`, and `exp` / `nbf` are valid. `aud=account` alone is not enough: every client in the realm has it. Cache JWKS by `kid` for 15 minutes, and refresh once on an unknown `kid`.

## Errors from the edge

| HTTP | Body | When |
|---|---|---|
| 302 | `Location` to `https://filenkov.store/auth/login?return_to=…` | Anonymous browser navigation. `return_to` is built from the request and limited to configured hosts. |
| 401 | `{"error":"unauthorized"}` | Anonymous on `/api/*`, `/users*`, WebSocket |
| 403 | `{"error":"forbidden"}` | Signed in, role does not allow |
| 403 | `{"error":"blocked"}` | Account disabled in idp |
| 404 | `{"error":"not_found"}` | No route, including `deny` |
| 503 | `{"error":"auth_unavailable"}` | idp or JWKS unavailable |
| 429 | `{"error":"rate_limited"}` | Above the per-IP budget of the host |
| 502 | `{"error":"bad_gateway"}` | Upstream did not answer |
| 504 | `{"error":"gateway_timeout"}` | Upstream sent no response header within the route timeout |

`/admin` answers in the same envelope, with its own values ([gateway message contract](../gateway/API/api-contract.md)).

Names `X-User-Id` and `X-Storage-Role` are not accepted.
