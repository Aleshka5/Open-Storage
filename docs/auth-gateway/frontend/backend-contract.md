# resume-page — backend contract

The only identity call is gateway `GET /auth/session`. Shape and errors: [gateway message contract](../gateway/API/api-contract.md).

```ts
type Session = {
  subject: string
  email: string
  name: string
  roles: string[]
  services: { service: string; level: null | 'family' | 'admin' | 'blocked' }[]
}
```

Catalog calls, all on `filenkov.store`, credentials via cookies:

| UI action | Call |
|---|---|
| Load the table | `GET /admin/users` |
| Change a service cell | `PUT /admin/users/{id}/roles/{svc}` with `{ "level": ... }` |
| Block or unblock the account | `PATCH /admin/users/{id}` with `{ "enabled": ... }` |
| Grant or revoke realm `admin` | `PUT /admin/users/{id}/admin` with `{ "value": ... }` |

The page does not call Keycloak, does not send `Authorization`, and does not parse role strings to build `services`. Gateway already returns `services`.

Showcase chat `POST /api/chat` and model switch ` /api/services` are gateway routes to other resources. The page calls those paths on its own host. It does not attach API keys.
