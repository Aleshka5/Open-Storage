# storage.filenkov.store

What this repository declares for the storage host. DNS, the certificate, a live gateway reload, and a probe of the public name are operator steps. They are not run from this tree.

## Declaration

The gateway block is [config.yaml](../../src/auth-gateway/gateway/config.yaml):

- `upstreams.storage` is `app:8000`
- host `storage.filenkov.store` with `service: storage`
- `/health` is `public`; `/**` is `service(storage, family, admin)`
- `timeouts.response_header` is `30m` on that host

`services` includes `storage`, so `policy.Parse` accepts `service(storage, family, admin)`. The product route table is owned by [upstreams](../auth-gateway/external-contracts/upstreams.md).

Response-header values on the other hosts in that same file, locked as they stand: `filenkov.store` and `id.filenkov.store` use the default `60s`; `image.filenkov.store` and `audio.filenkov.store` also declare `30m`; `rag.filenkov.store` is `5m`; `observer.filenkov.store` is `5m`.

A realm role `admin` with no `svc:storage:*` role does not pass `service(storage, family, admin)`. The host has no separate `policy: admin` route.

The realm roles `svc:storage:admin`, `svc:storage:family`, and `svc:storage:blocked` are in [realm.json](../../src/auth-gateway/idp/realm.json). No other `svc:storage:*` name is declared there.

The proxy name is in the shared host group in [Caddyfile](../../deploy/auth-gateway/Caddyfile). That group proxies to `127.0.0.1:8083` and imports `secure` (HSTS only). `http://storage.filenkov.store` redirects to `https://`. The proxy sets no second security header ([ADR-0001](../auth-gateway/adrs/1-edge-in-one-process.md)).

## What locks it

- [storage_host_test.go](../../src/auth-gateway/gateway/internal/config/storage_host_test.go) reads `config.yaml` and `realm.json` and fails if the declaration above changes.
- [edge_test.go](../../src/auth-gateway/gateway/internal/edge/edge_test.go) `TestStorageHostEnvelopes`: anonymous `/health` is forwarded, anonymous `/api/files` is `401 {"error":"unauthorized"}`, a stranger is `403 {"error":"forbidden"}`, `svc:storage:blocked` is `403 {"error":"blocked"}`, and `svc:storage:family` and `svc:storage:admin` are forwarded.
- [policy_test.go](../../src/auth-gateway/gateway/internal/policy/policy_test.go) covers `policy.Blocked` for `storage`.

[verify-storage-host.sh](../../scripts/verify-storage-host.sh) curls a `BASE_URL` and prints each status and body. It supplies no credentials. A row it did not send is not a pass.
