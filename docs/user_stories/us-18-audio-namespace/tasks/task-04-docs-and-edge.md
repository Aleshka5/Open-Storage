> **ID:** US-18 task-04
> **Status:** DONE
> **Specs:** [ADR-0012](../../../../adrs/12-audio-namespace.md), [upstreams](../../../auth-gateway/external-contracts/upstreams.md), [docs/init.md](../../../init.md), [US-18](../init.md)

## Overview

The namespace page, the system map, and the gateway's network attachment. The route on `audio.filenkov.store` already exists in the gateway config. This task attaches `audio_network` the way the gateway attaches an external product network, and records where the legacy ASR documents disagree. It does not copy that docs tree and does not restate the route.

## Goals

- `docs/audio/init.md` is short, in English, and links a fact instead of copying it. The schema is Mermaid with subgraphs for this namespace, the gateway hop, and `common`.
- [docs/init.md](../../../init.md) has an `audio` block and a link to the gateway.
- [upstreams](../../../auth-gateway/external-contracts/upstreams.md) gains the network attachment (`audio_network`) on the existing audio rows. The route text stays where it is.
- `deploy/auth-gateway/docker-compose.yaml` declares `audio_network` with `external: true` and the gateway service joins it.
- Mismatches between the legacy ASR documents and this namespace are a table in `docs/audio/init.md`. The legacy files are not rewritten.

## Non-goals

- Editing the gateway so `X-Auth-Subject` is a UUID.
- Changing upstream strings `audio-api:8000` and `frontend:80`.
- Copying `../ASR-Service/docs/`.
- A per-service API contract page. Endpoint behaviour stays owned by the legacy tree until a later page.

## Definition of Done

- [x] `docs/audio/init.md` exists and names the legacy files that disagree.
- [x] `docs/init.md` lists the `audio` namespace.
- [x] `upstreams.md` names `audio_network` and does not gain a second copy of the route.
- [x] The gateway compose joins `audio_network` (`external: true`).
- [x] `src/auth-gateway/gateway/config.yaml` upstream strings are unchanged.
