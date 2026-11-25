> **ID:** US-18
> **Status:** IN PROGRESS
> **Specs:** [ADR-0012](../../../adrs/12-audio-namespace.md), [identity v1](../../auth-gateway/external-contracts/identity-v1.md), [upstreams](../../auth-gateway/external-contracts/upstreams.md), [repository layout](../../repository-layout.md)

## Overview

ASR-Service becomes the `audio` namespace of this repository. The code moves from `../ASR-Service` to `src/audio/`, the deployment to `deploy/audio/`, and `audio-api` is put on the identity header this repository's edge already writes. The move is a port, not a copy: ASR-Service was written against `X-Auth-User-Id`, and this repository's edge writes `X-Auth-Subject`.

The old tree stays in place. Deleting it is not this story. Moving the tree is [task-01](tasks/task-01-layout.md); the network and data wiring is [task-02](tasks/task-02-compose.md); the identity port is [task-03](tasks/task-03-identity.md); the namespace page and the gateway network attachment are [task-04](tasks/task-04-docs-and-edge.md).

What the product does is not restated here. Endpoint behaviour stays in the old tree's `docs/` until a later page owns it. [audio/init.md](../../audio/init.md) is the namespace entry once task-04 writes it.

## Locked decisions

| # | Decision |
|---|---|
| D1 | Namespace `audio`, not `asr`. Code `src/audio/<service>`, deploy `deploy/audio/`, docs `docs/audio/`. Not a submodule. |
| D2 | Containers `audio-<service>`. Networks: `audio_network` (gateway hop), `audio_internal` (workers, qdrant), `common_network` (mongo, minio, rabbit, redis). No audio-edge. Service DNS names unchanged so gateway upstreams `audio-api:8000` and `frontend:80` stay. |
| D3 | Common data as today: mongo db `audio`, bucket `audio`, rabbit, redis GPU lease. Qdrant moves off `common_network` into this namespace. New qdrant and hf volumes are empty. Do not dump or delete existing mongo/minio data. |
| D4 | Identity v1 only: `X-Auth-Subject`, canonical lower-case UUID. No compatibility headers ([ADR-0001](../../../adrs/1-one-contract-version.md)). D6-style external condition: the edge must write a UUID subject; this story does not change the gateway issuer. |
| D5 | Product behaviour unchanged: endpoints, queues, models, phrase chat, voice note, nicks, error envelope, microphone policy already in gateway `config.yaml`. |
| D6 | `deploy/audio/.env` is the only secret file. `.env.example` has no real secret. |

## Goals

- `make doctor` in `deploy/audio/` fails when a required key is empty, and `podman compose config` parses the file.
- `audio-api` reads only `X-Auth-Subject`. A missing or non-UUID subject is `401 IDENTITY_MISSING`. A request that sends only `X-Auth-User-Id` is `401`.
- `rg 'X-Auth-User-Id|X-Auth-Role|X-User-Id|X-Storage-Role' src/audio deploy/audio docs/audio` finds nothing.
- The old `../ASR-Service` tree is still present.

## Non-goals

- Deleting `../ASR-Service`.
- Redesign of the product: endpoints, queues, models, phrase chat, voice note, nicks, the error envelope.
- Role checks inside `audio-api`. The gateway already enforces `svc:audio`.
- Changing gateway identity issuance so that `X-Auth-Subject` becomes a UUID.
- Copying Qdrant storage or Hugging Face weights.
- A second live header contract.

## User Story

**As** the operator, I want the audio product to be a namespace of this repository on identity v1, so that one compose file brings it up beside `common` and the gateway, without a second header contract.

**Acceptance**

- `src/audio/{audio-api,diarizer,asr-worker,frontend}` holds the service code. Tests sit inside each service. `.venv`, `node_modules`, `dist`, caches and `.env` are not in the tree.
- `deploy/audio/{.env.example,Makefile,docker-compose.yaml}` exists. Compose service names are `audio-api`, `diarizer`, `asr-worker`, `frontend`, `qdrant`. Container names are `audio-audio-api`, `audio-diarizer`, `audio-asr-worker`, `audio-frontend`, `audio-qdrant`. No `ports:` entry.
- `audio_network` is created by this compose and attached to the gateway as `external: true`. `qdrant` is only on `audio_internal`. `frontend` is only on `audio_network`. Workers and `audio-api` join `common_network`.
- Qdrant storage and Hugging Face weight volumes are named and empty. The Mongo database `audio` and the MinIO bucket `audio` are not dumped or deleted.
- A request with `X-Auth-Subject` set to a canonical UUID is accepted. The same request with only `X-Auth-User-Id`, or with a non-UUID subject, or with no subject, is `401 IDENTITY_MISSING`.
- `make doctor` exits non-zero when a required key is empty.
- The running GPU stand is not part of this change. Acceptance that needs a live GPU, loaded models, or `make up` stays open.
- `../ASR-Service` is not deleted.

## Definition of Done

- [x] ADR-0012 exists and [adrs/init.md](../../../adrs/init.md) links it before any code moves.
- [x] `src/audio/` holds the four services. The old tree is still on disk.
- [x] `deploy/audio/` holds `.env.example`, `Makefile` and `docker-compose.yaml`. `docker compose config` succeeds. `podman` is not installed, so `podman compose config` was not run. `make doctor` fails on an empty required key.
- [x] The gateway compose joins `audio_network` as `external: true`. Upstream strings in `config.yaml` are unchanged.
- [x] `docs/audio/init.md` exists. [docs/init.md](../../init.md) draws the block. [upstreams](../../auth-gateway/external-contracts/upstreams.md) records the network attachment and does not restate the route.
- [x] The v1 port is locked by tests: missing subject, non-UUID subject, and a request that sends only the pre-v1 user header are `401 IDENTITY_MISSING`. `/health` needs no identity. Object keys stay `u/{uuid}/`.
- [x] Mismatches between the legacy ASR docs and this namespace are recorded in [audio/init.md](../../audio/init.md), not silently rewritten. The legacy docs tree is not copied.
- [x] `rg` for the pre-v1 header names under `src/audio`, `deploy/audio` and `docs/audio` finds nothing.
- [ ] The old repository is deleted only after a later acceptance of the live stand. Not this change.
- [ ] The GPU stand (`make up`, model download, a live transcription) is not run here.

## Verification recorded

| Service | Result |
|---|---|
| `audio-api` | 178 passed, 14 skipped |
| `diarizer` | 39 passed, 6 skipped |
| `asr-worker` | 65 passed, 1 skipped |

On this host `ffprobe` is absent and `/proc/self/status` does not exist. The seven upload tests and the RSS test skip for that reason, the same way the existing ffmpeg cases skip. Identity tests passed. A one-off `pytest --cov=app` on `audio-api` reports 69% line coverage. The uncovered lines are the real Mongo, MinIO, RabbitMQ, Qdrant and ffprobe adapters, which the suite replaces with fakes. No coverage config was added.

`make doctor` exits 2 when `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `HF_TOKEN` or `RABBITMQ_URL` is empty. With those keys set, `docker compose config` succeeds. `podman` is not on `PATH`.

Not run: `make up`, image build, model download, a live transcription. The D4 condition stands: the edge writes the Keycloak `sub` in `X-Auth-Subject`, which is not a UUID, and `audio-api` refuses a non-UUID subject.
