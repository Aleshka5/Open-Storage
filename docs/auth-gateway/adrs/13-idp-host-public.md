## Status

Accepted

## Decision

`id.filenkov.store` is a public name. The proxy sends it to the gateway on `127.0.0.1:8083` with the other gateway hosts. It does not import the `lan` snippet.

`meet.filenkov.store` and `hermes.filenkov.store` keep that gate.

## Rejected

Leaving the `remote_ip` allow-list on `id.`. A browser off the LAN and off the tunnel then gets `403` before Keycloak, so the Google broker redirect cannot finish.

Publishing the Keycloak port itself. TLS still ends at the proxy. The gateway stays the only hop, with `identity: passthrough` and `policy: public` on that host.

## Cost

The Keycloak console and the broker are reachable from any source that can open 443. The console still requires Keycloak’s own login. Registration stays off. Google stays the only login. Brute-force protection on the realm is unchanged.

## Because

The issuer URL is where Google sends the browser back. A gate on that name makes sign-in a LAN feature. The name is already the public issuer, and the certificate is already a public ACME certificate.
