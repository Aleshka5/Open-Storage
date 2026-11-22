## Status

Accepted

## Decision

Routing, policy, and proxying run in the gateway process. The proxy only terminates TLS.

## Rejected

Caddy `forward_auth` plus a separate auth service. `oauth2-proxy` in front of each app. `caddy-security`.

## Cost

This namespace owns the proxy code. The limit is 2000 lines of Go and the runtime invariants in the gateway external contract.

## Because

The route and its policy are one entry in one file. A subrequest on every call adds a place for WebSocket upgrade to fail. Off-the-shelf proxies inject their own header names. A Go table test covers host × path × role. A Caddyfile does not.
