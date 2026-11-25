> **ID:** US-18 task-03
> **Status:** DONE
> **Specs:** [identity v1](../../../auth-gateway/external-contracts/identity-v1.md), [ADR-0001](../../../../adrs/1-one-contract-version.md), [US-18](../init.md)

## Overview

`audio-api` reads `X-Auth-Subject` only. The owner value must be a canonical lower-case UUID. A missing subject, a non-UUID subject, or a request that sends only `X-Auth-User-Id` is the existing `401 IDENTITY_MISSING`. `audio-api` does not check roles. Workers keep `owner_user_id` from queue messages. Object keys stay `u/{uuid}/`.

D4 is an external condition, not work in the gateway: the edge must write a canonical lower-case UUID in `X-Auth-Subject`. This task does not change the gateway issuer. The same condition is [US-16](../../us-16-rag-namespace/init.md) D6.

## Goals

- `get_current_owner` and the voice-note upgrade read `X-Auth-Subject`.
- A UUID with upper-case hex is accepted and stored lower-case.
- Tests that used `X-Auth-User-Id` send `X-Auth-Subject`. One test sends only `X-Auth-User-Id` and expects `401 IDENTITY_MISSING`.
- `/health` needs no identity.
- `X-Auth-User-Id`, `X-Auth-Role`, `X-User-Id` and `X-Storage-Role` are gone from `src/audio`, including comments in the frontend.
- Literal `minioadmin` and `guest:guest` defaults in service settings are removed. Tests that need a credential pass it explicitly.

## Non-goals

- Role checks inside `audio-api`. The gateway already enforces `svc:audio`.
- Header authentication on `diarizer` or `asr-worker`.
- Changing `src/auth-gateway/gateway/config.yaml` so the subject becomes a UUID.
- Verifying the bearer JWT. `audio-api` trusts the header because the gateway is the only path onto `audio_network`.

## Definition of Done

- [x] `rg 'X-Auth-User-Id|X-Auth-Role|X-User-Id|X-Storage-Role' src/audio deploy/audio docs/audio` finds nothing.
- [x] A test proves a request with only the pre-v1 user header is `401 IDENTITY_MISSING`.
- [x] A test proves a missing subject and a non-UUID subject are `401 IDENTITY_MISSING`.
- [x] A test proves an upper-case UUID is stored lower-case.
- [x] `/health` answers without an identity header.
- [x] Workers still take `owner_user_id` from the message body.
