> **ID:** US-16
> **Status:** TODO
> **Specs:** [ADR-0009](../../../adrs/9-rag-namespace.md), [identity v1](../../auth-gateway/external-contracts/identity-v1.md), [upstreams](../../auth-gateway/external-contracts/upstreams.md), [repository layout](../../repository-layout.md)

## Overview

RAG-Chat becomes the `rag` namespace of this repository. The code moves from `~/projects/RAG-Chat` to `src/rag/`, the deployment to `deploy/rag/`, the docs to `docs/rag/`, and the stack is put on the identity contract this repository's edge already writes. The move is a port, not a copy: RAG-Chat was written against `X-Auth-User-Id` and `X-Auth-Role`, and this repository's edge writes `X-Auth-Subject` and `X-Auth-Roles`.

The old repository stays in place until the new stand passes its acceptance, then it is deleted. Moving the tree is [task-01](tasks/task-01-layout.md); the network and data wiring is [task-02](tasks/task-02-compose.md); the identity port is [task-03](tasks/task-03-identity.md) and is the part that decides whether the move works.

What RAG is as a product is not restated here. The old tree's `docs/` is the ground truth for behaviour until the port copies it across; [rag/init.md](../../rag/init.md) is the entry once it does.

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | Namespace `rag`, code `src/rag/<service>`, deploy `deploy/rag/`, docs `docs/rag/`, per [ADR-0009](../../../adrs/9-rag-namespace.md). The legacy repository is neither a submodule nor a nested checkout. | A second repository, or a namespace named `rag-chat` |
| D2 | Containers are `rag-<service>`; the namespace network is `rag_network`, created here and `external: true` to the gateway; `rag_internal` stays service-to-service. | Keeping `rag_edge`, whose name belongs to the old compose |
| D3 | Mongo is the `common` server, database `rag`, reached as `mongo:27017`. MinIO is `minio:9000` (bucket `storage`), RabbitMQ is `rabbit:5672`, both from `common`. Qdrant stays in this namespace as `rag-qdrant`. | The `rag-mongo` alias, a private Mongo container, Qdrant in `common` |
| D4 | OCR and embedding move into this namespace and leave `models_network`. The stack joins `common_network`, `rag_internal` and `rag_network` and no other network. | Staying on Switch-Service's `models_network` |
| D5 | The edge writes identity v1 for this host. RAG reads `X-Auth-Subject` as the user key and `X-Auth-Roles` for the role family. `X-Auth-User-Id`, `X-Auth-Role`, `X-User-Id` and `X-Storage-Role` are removed from every service, test and doc. | A compatibility header set, which [ADR-0001](../../../adrs/1-one-contract-version.md) forbids |
| D6 | The gateway must write a value in `X-Auth-Subject` that this product can store as `user_id` without a key migration: a canonical lower-case UUID, stable per person. This is an external condition of the move, not a change made here. | Migrating every Mongo document and Qdrant point from UUID to the Keycloak `sub`, which is not a UUID |
| D7 | `deploy/rag/.env` is the only place a secret lives; the existing RAG-Chat `.env` is copied in for the stand and `.env.example` is rewritten with the new keys. No literal secret in a committed file. | Carrying `.env` into git, or shipping an example that names a real value |

## Goals

- `make up` in `deploy/rag/` starts the whole stack against `common`, with no container named without the `rag-` prefix and no `models_network` attachment.
- A file uploaded through `rag.filenkov.store` reaches `ready`, and a question returns an SSE answer, with identity taken only from v1 headers.
- `rg 'X-Auth-User-Id|X-Auth-Role\b|X-User-Id|X-Storage-Role' src/rag deploy/rag docs/rag` finds nothing.
- The old `~/projects/RAG-Chat` is deleted only after every acceptance item below holds.

## Non-goals

- Changing what the product does. Endpoints, chunking, batching (16), OCR, embedding and the SSE shape stay as the old tree's `docs/` says.
- A data migration from the old `rag-mongo` and `qdrant-data` volumes. The stand starts empty; a cutover of existing documents is a later story, like [US-08](../us-08-data-cutover/init.md) was for storage.
- Editing the gateway and idp for D6. That is a separate change in the auth-gateway namespace, and this story only records the condition.
- The frontend beyond its port to v1: no redesign, no theme work.

## User Story

**As** the operator, I want the RAG product to be a namespace of this repository on the same identity contract as every other host, so that one `make up` brings it up, one sign-in reaches it, and the old repository can go.

**Acceptance**

- `git ls-files src/rag deploy/rag docs/rag` lists the services, the four deploy files and the namespace docs; `git ls-files | grep -c '^src/RAG-Chat/'` is `0`.
- `podman ps --format '{{.Names}}'` shows `rag-rag-edge`, `rag-file-collector`, `rag-processor`, `rag-deletion-worker`, `rag-chat`, `rag-frontend`, `rag-embedding`, `rag-ocr`, `rag-qdrant` and no RAG container published to a host port.
- `podman inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' rag-rag-edge` prints `rag_network` and `rag_internal`; `rag-file-collector` also prints `common_network`; no container prints `models_network`.
- `podman exec rag-chat printenv | grep -E 'MONGODB_URI|S3_ENDPOINT|RABBITMQ_URL'` prints `mongo:27017`, `minio:9000` and `rabbit:5672`.
- A request to `rag.filenkov.store/api/files` with only `X-Auth-Subject` set to a UUID and `X-Auth-Roles` set to `svc:rag:family` answers `200`; the same request with `X-Auth-User-Id` instead answers `401`.
- A request with `X-Auth-Roles: svc:rag:blocked` answers `403`; the same with `X-Auth-Roles` empty answers `403` at the edge, never reaching the service.
- The old tree's `docs/mvp.md` checklist passes against the new host, with `X-Auth-User-Id` replaced by `X-Auth-Subject` in every check and `X-Auth-Role: BLOCKED` replaced by `X-Auth-Roles: svc:rag:blocked`.
- `cd deploy/rag && make doctor && make up` succeeds from empty volumes after `deploy/common` is up.

## Definition of Done

- [ ] ADR-0009 exists and `adrs/init.md` links it before any code moves.
- [ ] `docs/rag/` holds `init.md`, the per-service pages, the API contract and the external contract, in English, each linking a fact rather than copying it.
- [ ] `docs/init.md` draws the `rag` block and [upstreams](../../auth-gateway/external-contracts/upstreams.md) names it; the mismatch rows that disagree are recorded, not silently fixed.
- [ ] `deploy/rag/` holds `.env.example`, `Makefile` and `docker-compose.yaml`, passes `podman compose config`, and `make doctor` fails on an empty required key.
- [ ] The v1 port is locked by tests: a test per removed header name, and a test that `svc:rag:blocked` is `403`.
- [ ] The mismatch between the old `docs/gateway.md` and identity v1 is recorded in [rag/init.md](../../rag/init.md#mismatches) with the legacy file that says it.
- [ ] The old repository is deleted only after the acceptance items hold, and the deletion is its own commit or its own line in the report.
