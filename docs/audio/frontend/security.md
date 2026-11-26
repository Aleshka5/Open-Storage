# audio frontend — security

The page does not hold tokens, does not read the session cookie, and does not know secrets.

- One `GET /api/me` per load decides the gate. `401` is a guest. `403` is a signed-in account the API refused. Anything else that is not `200` is an error with Reload.
- A guest sees sign-in. The link is the hub, `https://filenkov.store/auth?return_to=<this page>`. This page has no sign-in form.
- Sign out navigates to the hub. `POST /auth/logout` is apex-only ([gateway API contract](../../auth-gateway/gateway/api-contract.md)), so this host does not call it.
- The workspace mounts only after `GET /api/me` returns `200`. Hiding it is not the enforcement. The gateway policy on `/api/**` is.
- The theme cookie is the preference in [brand book §1](../../brand-book/init.md). It is not a credential. The page does not write the theme to `localStorage`.
- `VITE_API_BASE_URL` is the only client build variable. It defaults to empty. A set value is public.
