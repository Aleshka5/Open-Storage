# proxy — external contract

What the edge requires, and the rules of talking to its neighbors. Files and certificates are in [init](init.md).

## Environment

The proxy is the host's systemd Caddy, not a compose service ([ADR-0005](../adrs/5-port-from-auth-service.md)). It reads no `.env`.

| Fact | Required | Use |
|---|---|---|
| `/etc/caddy/Caddyfile` | yes | Symlink to [deploy/auth-gateway/Caddyfile](../../../deploy/auth-gateway/Caddyfile). The file in git is the live file. |
| `/var/lib/caddy` | yes | ACME account, issued certificates, the local CA root and key. |
| `/usr/bin/caddy` | yes | 2.11. `make caddy-check` runs `caddy validate` against it. |
| Ports 80, 443 | yes | Bound on exactly `192.168.1.102` and `10.10.0.1` (`default_bind`). |
| `admin off` | yes | No admin API. A change is a file edit plus `systemctl restart caddy`. `caddy reload` posts to that API, so it cannot run. |
| Outbound 80 | for public names | ACME HTTP-01. Blocked, a name serves nothing and the failure is a TLS error on the client. |

## Gateway

One upstream for every SSO host, for `id.`, and for `demo.`: `127.0.0.1:8083`, a host loopback port. Two consequences:

- The proxy must run on the host. A container cannot reach the host's loopback ([ADR-0005](../adrs/5-port-from-auth-service.md)).
- Nothing else may publish 8083. [`.env.example`](../../../deploy/auth-gateway/.env.example) sets `GATEWAY_PORT=8083`, and the Makefile declares the same default, so `make up` publishes 8083 with or without the env line. Compose falls back to `8080` only when the variable is unset, and this file does not use `8080`.

The gateway is not on a shared network with the proxy and does not need to be: the only link is that port. The proxy does not know route names, policies, or hosts' header settings; it forwards to the same address for the SSO hosts and for `id.`, and lets `Host` decide.

`id.filenkov.store` uses that same port and has no `lan` gate ([ADR-0013](../adrs/13-idp-host-public.md)). Any source that can open 443 reaches the gateway, which forwards to Keycloak. The certificate is a public ACME certificate because the name is the issuer URL.

`meet.filenkov.store` goes to `127.0.0.1:8000`. It is not an SSO host and not a gateway upstream.

## Hosts outside the gateway

| Host | Upstream | Certificate | Auth |
|---|---|---|---|
| `meet.filenkov.store` | `127.0.0.1:8000` | `tls internal` | LAN / WireGuard gate. No SSO. The gateway has no `meet` host. |
| `hermes.filenkov.store` | `127.0.0.1:9119` | `tls internal` | LAN / WireGuard `remote_ip` gate in Caddy. No SSO. Keeps its own login. |
| `lite-llm.filenkov.store` | `127.0.0.1:4000` | ACME HTTP-01 | None at the edge. |

`hermes` is a recorded deviation from the contract's original shape, in [ADR-0005](../adrs/5-port-from-auth-service.md). The gate is not optional: without it the dashboard is on the internet with no SSO in front. Do not widen it without the owner's agreement.

## The `lan` gate

One snippet, imported by `meet` and `hermes`. `id.` does not import it. It is an allow-list of source addresses:

```text
@lan remote_ip 10.10.0.1 10.10.0.2 10.10.0.4 192.168.1.0/24 127.0.0.1
```

A source outside it gets `403` with a one-line body. Every address in that list is a deliberate entry: the WireGuard server and the peers on it, the LAN, loopback. Adding a subnet widens every host that imports the snippet. The `403` is not a routing error and will not appear in the gateway's log, because the request never reaches it.

## Upstairs

The router forwards 80, 443, and 22 to `192.168.1.102` by DHCP reservation. The proxy believes nothing about that: it binds the two local addresses and does not look at the router. Whether the name is reachable from the internet is therefore two independent facts — a DNS A record, and a forward — and a failure of either looks the same to a client.

`meet` has no A record by design: the name lives in `/etc/hosts` and in dnsmasq. It is reachable from the LAN and the tunnel only, and its certificate comes from Caddy's local CA.

## Certificates

| Class | Where the trust comes from | What breaks |
|---|---|---|
| Public | ACME HTTP-01, one certificate per name, no wildcard | A missing A record, or closed port 80 |
| Internal (`meet`, `hermes`) | Caddy's local CA at `/var/lib/caddy/pki/authorities/local/root.crt (root-owned; read it with sudo)`, installed in the client's store | A certificate error, not a `404`. New clients need the root. |

No wildcard is deliberate: one A record per name means one missing record fails one host, and a compromise of one name does not hand out the rest.

## Headers this service sets

| Header | Set here | Note |
|---|---|---|
| `Strict-Transport-Security` | yes, every site | `max-age=31536000; includeSubDomains` |
| `Server` | removed | Not advertised |
| `Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` | **no** | Owned by the gateway, per host ([gateway contract](../gateway/external-contracts.md), [ADR-0008](../adrs/8-idp-host-frame-self.md)) |

A duplicate header is a defect: browsers intersect the policies, so a second value silently narrows the first. Nothing in the Caddyfile may add a header the gateway already sets, with the single exception of HSTS, which only the proxy sets.

Observed on the live edge, from a LAN client: every SSO host answers with exactly one HSTS value and no `Server`; `id.` carries no `x-frame-options` (`frame: self`); `meet` carries neither `x-frame-options` nor `referrer-policy` because its upstream answers `200` itself.

## When it fails

| Symptom | Check |
|---|---|
| Certificate error on `meet` or `hermes`, other hosts fine | Local CA root not installed on this client, or `/var/lib/caddy` was wiped |
| `403 "Access is limited to the LAN and the WireGuard tunnel"` | Source address not in `@lan`. A container's own IP, not the client's, if the request was forwarded on |
| `502` from the proxy itself (has a `Server` header, no HSTS) | The upstream port has no listener. `curl -H 'Host: <fqdn>' http://127.0.0.1:8083/<path>` to separate this from a gateway answer |
| `404 {"error":"not_found"}` | Not the proxy. The host reached the gateway and the gateway has no route. |
| Redirect to `https://` loops | `default_bind` and the explicit `http://` block: a name in the redirect list and also served on 80 by something else |
| A new host 404s through the proxy but works direct | The name is missing from the site block or the HTTP redirect list. With `default_bind` Caddy adds neither. |
| Requests reach the wrong application | Two services on one name. Each site block has one upstream; a second `reverse_proxy` on the same name is a change to this contract. |

Changing the file: `caddy validate --config /etc/caddy/Caddyfile` (`make caddy-check`), then `systemctl restart caddy`. `admin off` leaves reload with nowhere to post. A restart drops connections. There is no compose step and no gateway restart in a proxy change.
