# demo

The infrastructure map. One static page, one network, one env file, one compose file. The decision is [ADR-0014](../../adrs/14-demo-namespace.md).

## Services

| Service | Container | DNS name | Port | Host publish | Networks |
|---|---|---|---|---|---|
| `frontend` | `demo-frontend` | `demo` | 80 | no | `demo_network` |

The gateway joins `demo_network` and forwards `demo.filenkov.store` to `demo:80`. `/health` is public. Every other path is `session`. The page itself is the map: Internet, Router, then this server, and each of those opens until a service or a Docker network member.

## Schema

```mermaid
flowchart LR
  P["proxy"]
  G["gateway"]
  F["demo :80"]

  P -->|"demo.filenkov.store → 127.0.0.1:8083"| G
  G -->|"demo_network"| F
```

`make up` in `deploy/demo/` creates `demo_network` and starts the page. Recreate the gateway after that network exists, or the gateway compose cannot attach.
