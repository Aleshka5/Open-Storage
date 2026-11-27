> **ID:** task-01
> **Status:** TODO
> **Specs:** [US-19](../init.md), [ADR-0011](../../../../adrs/11-gateway-joins-rag-network.md)

## Overview

The edge hop. `deploy/auth-gateway/docker-compose.yaml` joins `rag_edge`; the stack the `rag` namespace creates is `rag_network`. This task moves the gateway to `rag_network` and removes the legacy name, per [ADR-0011](../../../../adrs/11-gateway-joins-rag-network.md).

## Goals

- `deploy/auth-gateway/docker-compose.yaml` declares `rag_network` (`external: true`) and `rag_edge` is gone from the file.
- The gateway container is recreated and its networks are exactly `open_network`, `rag_network`, `models_network`, `deploy_auth_network`.
- `src/auth-gateway/gateway/config.yaml` is unchanged: host `rag.filenkov.store`, upstream `rag-edge:8080`, `policy: "service(rag, family, admin)"`, `/health` public.
- Once `rag-rag-edge` exists on `rag_network`, the gateway resolves it; until then `502 bad_gateway` is the expected answer, not a defect.

## Non-goals

- Removing the legacy containers and network: that is task-04, after the stack passes.
- Any change to the gateway's Go code, to the idp, or to the host's policy.

## Definition of Done

- [ ] `cd deploy/auth-gateway && make doctor` passes.
- [ ] `podman compose -f docker-compose.yaml config` shows `rag_network` and no `rag_edge`.
- [ ] `make up` in `deploy/auth-gateway/` recreates the gateway; `podman inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' auth-gateway_gateway_1` prints `rag_network`.
- [ ] `make verify` in `deploy/auth-gateway/` passes for the hosts it covers, and `https://storage.filenkov.store/health` is still `200`.
- [ ] The gateway log has no `lookup rag-edge ... no such host` row after this task and before the stack is up only as `502`, which is expected until task-03.
