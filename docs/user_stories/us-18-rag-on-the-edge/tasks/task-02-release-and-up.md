> **ID:** task-02
> **Status:** TODO
> **Specs:** [US-18](../init.md), [ADR-0010](../../../../adrs/10-published-images.md), [images.md](../../../images.md), [ADR-0011](../../../../adrs/11-gateway-joins-rag-network.md)

## Overview

Publish the eight `rag` images and start the stack on `rag_network`. The gateway already joins that network (task-01); this task gives it an upstream. Images are published per [ADR-0010](../../../../adrs/10-published-images.md), so `make up` pulls and does not build.

## Goals

- `make release` in `deploy/rag/` pushes `${REGISTRY}/rag/{rag-edge,file-collector,processor,deletion-worker,chat,frontend,embedding,ocr}` at today's date and moves `latest`.
- `make up` in `deploy/rag/` pulls those tags and starts all nine containers.
- `rag-rag-edge` is reachable as `rag-edge:8080` from the gateway container.
- No container publishes a host port and none joins `models_network`.

## Non-goals

- Granting roles and signing in: task-03.
- Removing the legacy stack: task-04.
- Any product behaviour or identity code change.

## Definition of Done

- [ ] `podman login registry.filenkov.store` exists on this host, or a documented reason is recorded for pulling without it (the registry is behind htpasswd in `deploy/registry-compose.yaml`).
- [ ] `cd deploy/rag && make doctor` passes: `.env` has every required key and `check-images` resolves the tag.
- [ ] `make release` completes; `podman images | grep 'registry.filenkov.store/rag/'` lists eight repositories at today's date.
- [ ] `make up` completes from the published images; `podman ps` lists `rag-rag-edge`, `rag-file-collector`, `rag-processor`, `rag-deletion-worker`, `rag-chat`, `rag-frontend`, `rag-embedding`, `rag-ocr`, `rag-qdrant`.
- [ ] `podman inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' rag-rag-edge` prints `rag_network` and `rag_internal`; `rag-file-collector` also prints `common_network`; no container prints `models_network`.
- [ ] `podman exec rag-chat printenv | grep -E 'MONGODB_URI|S3_ENDPOINT|RABBITMQ_URL'` prints `mongo:27017`, `minio:9000`, `rabbit:5672`.
- [ ] `podman exec auth-gateway_gateway_1 wget -qO- http://rag-edge:8080/health` answers `{"status":"ok"}`, and `curl https://rag.filenkov.store/health` answers `200`.
- [ ] If the registry or pypi is unreachable, `make rebuild-all` is the recorded fallback, and the report says which path ran and why.
