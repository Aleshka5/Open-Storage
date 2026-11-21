# ADR-0008 The idp host is frameable by itself

## Status

Accepted

## Decision

The `id.filenkov.store` host carries `frame: self`. Every response the gateway
produces for a host, not only the ones proxied from its upstream, takes
`X-Frame-Options` from that host's `frame` setting. `deny` stays the default.

## Rejected

Blanket `DENY` on the idp host, on the reading that an identity provider must
never be framed. Keycloak ships `check_session_iframe` — served at
`/realms/<realm>/protocol/openid-connect/login-status-iframe.html` — and its own
CSP (`frame-src 'self'`) is written for the case where a page on the realm's
origin frames it. Denying that frame breaks session polling, and the browser
reports it as `Timeout when waiting for 3rd party check iframe message`, not as
a frame error. The consequence lands on whoever tries to log in, with no
indication of the cause.

Exempting the host from security headers altogether. `frame: self` is narrower:
`X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy` still apply.

Leaving `X-Frame-Options` hardcoded to `DENY` on the gateway's own answers (the
`302` to login and the JSON errors) while reading it from the host on proxied
responses. Two code paths, two answers for one host, and the second one is a
defect nobody sees until an app frames a page that a non-signed-in caller
requested.

## Cost

`frame: self` on the idp host means a page on `id.filenkov.store` can frame a
page on `id.filenkov.store`, which is what the check-session iframe requires.
Pages on any other origin still cannot: `self` is not `ALLOW-FROM`, and the host
name space is one origin per host.

## Because

The host setting exists to describe what the host does, and Keycloak frames
itself as a documented part of the OIDC flows it serves. A default of `deny` is
correct for a host that is an application under identity v1; the idp is not one
(`identity: passthrough` already says so), and its session iframe is the reason.
