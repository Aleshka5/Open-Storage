# task-09 Realm as code

Story: [US-01](../init.md)

## Outcome

Realm `filenkov` matches the idp message contract: Google IdP (`IMPORT`, `kc_idp_hint`), `emailAsUsername`, duplicate emails forbidden, clients `gateway` and `gateway-admin`, roles `admin` plus `svc:*` for `storage`, `image`, `rag`, and `audio`, TTLs 5m / 7d / 30d, brute force on.

## Paths

- `src/auth-gateway/idp/realm.json`
- `src/auth-gateway/idp/theme/filenkov/`

## Done when

- `jq` reads `.realm`, the Google alias, and client ids.
- idp starts on an empty volume.
- The discovery document returns the expected issuer.
