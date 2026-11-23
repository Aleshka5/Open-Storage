> **ID:** US-07
> **Status:** TODO
> **Specs:** [gateway config](../../../src/auth-gateway/gateway/config.yaml), [gateway API contract](../../auth-gateway/gateway/api-contract.md), [idp roles](../../auth-gateway/idp/init.md), [identity v1](../../auth-gateway/external-contracts/identity-v1.md)

## Overview

`storage.filenkov.store` becomes a routed host on the new gateway. Most of it is already declared: the `storage` upstream (`app:8000`), the `services: [storage, …]` entry, the `storage.filenkov.store` host block with `service: storage`, `timeouts: { response_header: 30m }` and the route set, and the three realm roles `svc:storage:{admin,family,blocked}`. The site block is also in the repo's Caddyfile, and `/etc/caddy/Caddyfile` is a symlink to it. The remaining work is DNS, a real gateway restart against the new upstream, and proving the host end to end.

Tasks: [upstream and host block](tasks/task-01-host-block.md), [route set](tasks/task-02-routes.md), [timeout](tasks/task-03-timeout.md), [proxy site block](tasks/task-04-proxy.md), [DNS](tasks/task-05-dns.md), [roles](tasks/task-06-roles.md), [prove the host](tasks/task-07-verify.md).

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The gateway config is not edited for this host. The block in `src/auth-gateway/gateway/config.yaml` is the declaration; this story makes it true. A needed change is a finding, not a silent edit. | Rewriting the block to look like work |
| D2 | The upstream stays `app:8000` on `open_network`. The app publishes no host port, so the gateway is the only path in. | Publishing `:8000` as a second edge |
| D3 | `/health` is `public`; everything else is `service(storage, family, admin)`. A stranger is refused at the edge with `403 {"error":"forbidden"}`, and `svc:storage:blocked` gets `403 {"error":"blocked"}`. | A `session` policy on `/**`, which would admit every account and leave the service gate to the app |
| D4 | `timeouts.response_header` stays `30m` for this host, because a large download holds the response header until the first byte of the body. | The 60s default, which turns a large upload into a `504 gateway_timeout` |
| D5 | The site block lives in `deploy/auth-gateway/Caddyfile`, which `/etc/caddy/Caddyfile` symlinks to. The edit is to the repo file, and the host reloads it. | Editing the host file directly, which the symlink makes impossible and which would drift from git |
| D6 | Admin stays the app's check ([US-06 D10](../us-06-identity-v1/init.md)). The gateway does not add a `policy: admin` route for `/api/admin/**`. | A gateway admin route that denies a `svc:storage:admin` without realm `admin` |

## Goals

- `https://storage.filenkov.store/health` answers 200 without a session.
- A family account reaches every page; a stranger is refused at the edge.
- A large download completes past 60 seconds.

## Non-goals

- Any change to the gateway binary, the realm, or the app.
- Cutting over the data ([US-08](../us-08-data-cutover/init.md)).

## User Story

**As** a family member, I want `storage.filenkov.store` served by the gateway, so that one login at `filenkov.store` opens storage, and the edge refuses the accounts I closed.

**Acceptance**

- `curl -fsS https://storage.filenkov.store/health` answers 200 with no cookie.
- `curl -s -o /dev/null -w '%{http_code}' https://storage.filenkov.store/api/files` without a cookie answers `401` and the body is `{"error":"unauthorized"}`.
- A family account's browser gets 200 on `/` and on `/api/files`. A `svc:storage:blocked` account gets `403` with `{"error":"blocked"}` on both.
- An account with no storage role gets `403` with `{"error":"forbidden"}`.
- A download over a minute long completes, and the response's first byte arrives within the host timeout.
- `dig +short storage.filenkov.store` returns the host's address, and `caddy validate` passes on the repo file.
- `podman logs <gateway> | grep storage.filenkov.store` shows the request lines for the probes above.

## Definition of Done

- [ ] The host answers through the real gateway, not a stand.
- [ ] DNS resolves from outside the LAN as well as inside.
- [ ] The acceptance items above are recorded with their commands.
- [ ] Any mismatch between `config.yaml` and what the app needs is written as a finding, not fixed in passing.
