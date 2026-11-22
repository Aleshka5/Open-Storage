# ADR-0003 One session store

## Status

Accepted

## Decision

Sessions, logout-all, and not-before live in the identity provider. The edge does not add Redis or its own database. The browser holds a sealed cookie, not a server-side session record.

## Rejected

Redis for sessions or revocation. A signed but unencrypted cookie.

## Cost

The edge cannot kill one session by itself. The identity provider does that. Rotating the cookie key signs everyone out. That is the fast break-glass when the admin API is down.

## Because

A second store must be backed up, restarted, and kept in agreement with the provider. Encryption keeps the refresh token unreadable to the client.
