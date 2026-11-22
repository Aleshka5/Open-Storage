# idp — external contract

## Google

OAuth client type Web application. One authorized redirect URI:

`https://id.filenkov.store/realms/filenkov/broker/google/endpoint`

Variables: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.

`syncMode` stays `IMPORT`. `FORCE` changes `sub` between logins.

## Postgres

`idp_db`, Postgres 17, database `keycloak`, user `keycloak`, password `IDP_DB_PASSWORD`. Volume `idp_pgdata`. No published port. Code folder: `src/auth-gateway/postgres`. Schema migrations belong to the Keycloak image.

Backup: `pg_dump` daily to `backups/` on disk. Signing keys live in this database, so the dump is mandatory. Realm schema rollback is not supported. The rollback is restoring the dump.

Restore onto an empty volume, then start idp without `--import-realm`.

## Process

Image `quay.io/keycloak/keycloak:26.8.2`, pinned. Upgrade is a deliberate change of the tag in this contract and in compose, after a dump.

```text
KC_DB=postgres
KC_DB_URL=jdbc:postgresql://idp_db:5432/keycloak
KC_HOSTNAME=https://id.filenkov.store
KC_HTTP_ENABLED=true
KC_PROXY_HEADERS=xforwarded
```

Command: `start --import-realm`. Import is `ifResourceExists: SKIP` on an empty database. Realm file and theme are mounted read-only.

`--optimized` is not used: Keycloak refuses it on a first-ever start, and the first start builds the server itself. That is why an empty database takes about 60 seconds.

Import of a schema change: edit `realm.json`, recreate idp, confirm the issuer URL, sign in with Google, confirm `realm_access.roles`.

Drift check: export the live realm, drop `users`, `components`, and `id`, and diff against git. Anything else in the diff is an edit made outside git.

## When it fails

| Symptom | Cause |
|---|---|
| `Invalid parameter: redirect_uri` | Google redirect URI is not the broker endpoint |
| Cookie not found | `KC_PROXY_HEADERS=xforwarded` missing. Keycloak saw HTTP. |
| Login works, roles empty | Realm roles were not granted, or import did not apply |
| `sub` changes between logins | Google IdP `syncMode` is not `IMPORT` |
| First start is slow | Realm import and DB migrations. Up to about 60 seconds is normal. |
