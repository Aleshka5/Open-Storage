# ADR-0014 The infrastructure map is the demo namespace

## Status

Accepted

## Decision

The drill-down map of this host lives in this repository as the `demo` namespace. One network, one env file, one compose file, per [ADR-0008](8-common-data-services.md) and [repository-layout.md](../docs/repository-layout.md).

| Fact | Value |
|---|---|
| Namespace | `demo` |
| Code | `src/demo/frontend` |
| Deploy | `deploy/demo/` |
| Docs | `docs/demo/init.md` |
| Namespace network | `demo_network`, created here, `external: true` to the gateway |
| Host | `demo.filenkov.store`. Upstream `demo:80` |
| Policy | `session` on `/**`, `public` on `/health` |
| Container | `demo-frontend`. DNS name on `demo_network` is `demo`, so it does not collide with `frontend` on `audio_network` |
| Host publish | none |
| Data | none. The page does not join `common_network` |

The proxy adds the name to the public site block that already forwards to `127.0.0.1:8083`. The certificate is ACME HTTP-01, the same class as the other names in that block. The name needs an A record before Caddy can issue it. The page is a signed-in view: it names LAN addresses, the WireGuard port, and the Docker networks.

## Rejected

Serving the page from the resume host, which would mix the map into the apex site. Naming the container `frontend`, which is already the DNS name the gateway uses for audio. A public policy, which would publish the internal map without a session. `tls internal`, which would hide a name that is meant to have a public A record.

## Cost

The gateway compose names `demo_network` as external. `deploy/demo` has to create that network before the gateway container is recreated. The image is one more repository under `REGISTRY`.

## Risk

Until the A record exists, a Caddy restart will fail ACME for this name. The other names in the same site block keep the certificates they already hold; the new name does not serve until the record and a restart both exist.
