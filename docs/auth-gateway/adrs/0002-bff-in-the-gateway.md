# ADR-0002 BFF inside the gateway

## Status

Accepted

## Decision

The gateway is the OIDC client. Tokens stay in `HttpOnly` cookies. JavaScript never sees them.

## Rejected

A SPA as a public OIDC client with PKCE, holding tokens itself.

## Cost

Four `/auth` endpoints, and the gateway refreshes tokens for the user (one refresh in flight per subject).

## Because

Nine hosts share one parent domain. A cookie on that domain is one login. A SPA needs the token in each tab and CORS on every API, or a third-party cookie that browsers drop. XSS cannot read an `HttpOnly` token.
