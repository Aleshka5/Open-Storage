> **ID:** US-16 task-03
> **Status:** TODO
> **Specs:** [identity v1](../../../auth-gateway/external-contracts/identity-v1.md), [ADR-0001](../../../../adrs/1-one-contract-version.md), [US-16](../init.md)

## Overview

The port from the old identity to identity v1. This is the task that decides whether the move works, because the old tree refuses every request that does not carry `X-Auth-User-Id` as a UUID, and the edge never writes that name.

`rag_common/auth.py` and `chat/auth.py` are the only places a user is resolved; the edge copies the same headers upstream. Both change to read `X-Auth-Subject` and `X-Auth-Roles`. The role test becomes a substring test over the space-separated list, not an equality test against `X-Auth-Role`.

## Locked decision pulled from US-16

D6 is an external condition, not work in this repository: the gateway must write a canonical lower-case UUID, stable per person, in `X-Auth-Subject`. If the edge cannot satisfy it, this task stops and the story returns to a decision, rather than migrating every Mongo document and Qdrant point onto a non-UUID key.

## Goals

- `rag_common/auth.py`: `AUTH_USER_HEADER = "X-Auth-Subject"`, `AUTH_ROLES_HEADER = "X-Auth-Roles"`; a missing subject is `401`; `svc:rag:blocked` in the roles is `403`.
- `chat/auth.py` and `rag-edge`'s header forwarding follow the same two names.
- Every test that sends `X-Auth-User-Id` now sends `X-Auth-Subject`; a test per removed name asserts it is ignored.
- The old tree's `docs/gateway.md` is not carried over. Its facts that still hold are in [identity v1](../../../auth-gateway/external-contracts/identity-v1.md).

## Non-goals

- Changing the gateway, the idp or `realm.json`. The roles `svc:rag:*` already exist.
- Verifying the bearer JWT. The services trust headers because they are reachable only on `rag_network` and `rag_internal`.
- `X-Auth-Session` and the vault. RAG has no vault.

## Definition of Done

- [ ] `rg 'X-Auth-User-Id|X-Auth-Role\b|X-User-Id|X-Storage-Role' src/rag deploy/rag docs/rag` finds nothing.
- [ ] A test proves a request with only `X-Auth-User-Id` is `401`, and one with `X-Auth-Subject` is accepted.
- [ ] A test proves `X-Auth-Roles: svc:rag:blocked` is `403`, and `svc:rag:family` passes.
- [ ] A test proves a subject that is not a UUID is refused, so D6 is locked rather than assumed.
- [ ] The `/health` route on `rag-edge` and on each service needs no identity.
- [ ] `deploy/rag/.env.example` names no identity-era key.
