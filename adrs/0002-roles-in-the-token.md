# ADR-0002 Roles live in the token

## Status

Accepted

## Decision

Realm roles travel in the access token. The edge reads claims. There is no catalog service on the request path.

## Rejected

A user service that the edge calls for the role on every request.

## Cost

Keycloak Admin API is the only way to edit roles. "Last admin" and "service admin edits only their service" are checked in the gateway, because the Admin API account is shared. A removed role applies within the access-token TTL (5 minutes). The short TTL exists for that reason.

## Because

A catalog on the hot path adds a network call and a failure mode where "catalog down" becomes 503 for every product.
