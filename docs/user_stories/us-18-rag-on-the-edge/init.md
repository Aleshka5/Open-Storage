> **ID:** US-18
> **Status:** TODO
> **Specs:** [ADR-0009](../../../adrs/9-rag-namespace.md), [ADR-0011](../../../adrs/11-gateway-joins-rag-network.md), [ADR-0001](../../../adrs/1-one-contract-version.md), [identity v1](../../auth-gateway/external-contracts/identity-v1.md), [upstreams](../../auth-gateway/external-contracts/upstreams.md), [rag/init.md](../../rag/init.md), [images.md](../../images.md)

## Overview

The `rag` namespace is in this repository, tests green, and unreachable: `deploy/auth-gateway/docker-compose.yaml` joins a network named `rag_edge`, `deploy/rag/docker-compose.yaml` creates `rag_network`, and nothing builds the stack. This story makes `https://rag.filenkov.store` answer through one sign-in on identity v1, with no compatibility header and no second name for a network or a role.

What is missing is not product behaviour. It is three cuts: the edge hop, the stack's images, and the sign-in row a person needs before `403` becomes a page. The product itself is [rag/init.md](../../rag/init.md); the port onto v1 is [US-16](../us-16-rag-namespace/init.md) and is done at the code level.

## Locked decisions

| # | Decision | Rejected |
|---|---|---|
| D1 | The edge hop is the name [ADR-0009](../../../adrs/9-rag-namespace.md) records: the gateway declares `rag_network` `external: true` and joins only that. `rag_edge` is removed from `deploy/auth-gateway/docker-compose.yaml` in the same change. | Keeping `rag_edge` and renaming the stack's network to it, which makes the decision follow the old compose instead of replacing it |
| D2 | The old stack is cut over, not run beside the new one. `webstorage`-style coexistence is not used: the legacy `rag-chat_*` containers and the `rag_edge` network are removed after the new stand passes, and the gateway never joins two RAG networks. | Bridging `rag_edge` to `rag_network`, or running both stacks behind one host |
| D3 | The sign-in row is a realm role in the idp, not a gateway special case: `svc:rag:family` is granted through the existing Admin API (`/admin`), and the host keeps `policy: "service(rag, family, admin)"`. | A per-host allow-list in the gateway config, which [ADR-0002](../../../adrs/2-roles-in-the-token.md) rules out |
| D4 | `X-Auth-Subject` is consumed as it arrives. No `idp` mapping and no key migration: a subject that is not a canonical UUID is `401` in every RAG service. A realm whose users carry a non-UUID `sub` fails this story's acceptance, and the remedy is a realm change recorded in the auth-gateway namespace, not a RAG fallback. | Deriving a UUID in the edge (hash of `sub`), which invents a second identity and is not stable across realms |
| D5 | The stack runs from published images ([ADR-0010](../../../adrs/10-published-images.md)): `make release` in `deploy/rag/`, then `make up` on the same host. `make rebuild-all` is the fallback only when the registry or pypi is unreachable, and the fallback is recorded in the report, not in the docs. | A permanent local-build path, which leaves the stand unproven against what the registry serves |
| D6 | Embedding and OCR are part of the acceptance, not an optional profile: the story is done when an uploaded file reaches `ready`, which needs both. | A "light" stack without them, which would pass a request test and fail the product |

## Goals

- `https://rag.filenkov.store/health` answers `200 {"status":"ok"}` from `rag-rag-edge`, not `502 bad_gateway` from the gateway.
- One sign-in on `.filenkov.store` reaches the product: anonymous navigation gets `302` to `/auth/login`, a signed-in caller with `svc:rag:family` gets the SPA shell, and `svc:rag:blocked` gets `403 {"error":"blocked"}` at the edge.
- An upload through the host reaches `ready` and a question returns an SSE answer.

## Non-goals

- Product behaviour, endpoints, chunking, OCR, embedding and the SSE shape: unchanged, and still owned by the pages [US-16](../us-16-rag-namespace/init.md) names.
- A data cutover from the legacy `rag-mongo` and `qdrant_data` volumes. The stand starts empty; moving existing documents is a later story.
- The frontend beyond what v1 needs. No redesign and no theme work.
- The `storage` product's own identity rows.

## User Story

**As** the operator, I want `rag.filenkov.store` up on the same sign-in as every other host, so that a person signs in once and reaches the product, and the legacy stack can go.

**Acceptance**

- `podman inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' auth-gateway_gateway_1` prints `rag_network`, and `podman network ls` has no `rag_edge`.
- `podman ps --format '{{.Names}}'` shows `rag-rag-edge`, `rag-file-collector`, `rag-processor`, `rag-deletion-worker`, `rag-chat`, `rag-frontend`, `rag-embedding`, `rag-ocr`, `rag-qdrant`, and no `rag-chat_*` container.
- `curl https://rag.filenkov.store/health` is `200 {"status":"ok"}` and the gateway log row for that path carries `status=200`, not `502`.
- `./scripts/verify-storage-host.sh`-shaped probe for this host: anonymous `/api/files` is `401 {"error":"unauthorized"}`, `svc:rag:family` is forwarded (`200` or the service's own body), `svc:rag:blocked` is `403 {"error":"blocked"}`.
- A request carrying `X-Auth-User-Id` instead of `X-Auth-Subject` answers `401` from `file-collector`, not `200`.
- An uploaded PDF reaches `ready` in Mongo and its chunks are in the `documents` Qdrant collection; a question streams SSE deltas.
- `rg 'X-Auth-User-Id|X-Auth-Role\b|X-User-Id|X-Storage-Role' src/rag deploy/rag docs/rag` finds nothing.
- `cd deploy/rag && make doctor && make up` succeeds from empty volumes with `deploy/common` up and the gateway already running.

## Definition of Done

- [ ] [ADR-0011](../../../adrs/11-gateway-joins-rag-network.md) records D1 and is linked from `adrs/init.md`.
- [ ] `deploy/auth-gateway/docker-compose.yaml` names `rag_network`; `deploy/auth-gateway/Makefile doctor` and `podman compose config` pass; the gateway is recreated and `make verify` still passes for `storage.` and `filenkov.store`.
- [ ] `docs/rag/init.md` Mismatches no longer carries the `rag_edge` row; the row is replaced by the fact that the gateway joins `rag_network`, because the mismatch is closed.
- [ ] The `svc:rag:family` grant is applied to the operator's account through `/admin` and the fact is recorded in the report; no secret and no password is written to a document.
- [ ] `make release` in `deploy/rag/` pushes all eight repositories at today's date and moves `latest`; `make up` pulls them and every container is `healthy` or has no health check.
- [ ] The legacy stack is removed (`podman rm` the `rag-chat_*` containers, `podman network rm rag_edge`) after the acceptance above holds, and its volumes are left in place for the later cutover story.
- [ ] `docs/rag/README.md` and [rag/init.md](../../rag/init.md) describe the running stand; no page says a stack that is up is unverified.
