> **ID:** US-16 task-02
> **Status:** TODO
> **Specs:** [ADR-0009](../../../../adrs/9-rag-namespace.md), [common](../../../common/init.md), [US-16](../init.md)

## Overview

The compose file, the env example and the Makefile put the stack on the networks and data services the namespace is allowed to use: `rag_network`, `rag_internal`, `common_network`, Mongo and RabbitMQ from [common](../../../common/init.md), MinIO's `storage` bucket, Qdrant local. Container names take the `rag-` prefix.

## Goals

- `deploy/rag/docker-compose.yaml` defines nine services on the three networks and no host port.
- `MONGODB_URI` points at `mongodb://mongo:27017/rag`; `S3_ENDPOINT` at `http://minio:9000`; `RABBITMQ_URL` at `amqp://rabbit:5672/`.
- `QDRANT_URL` points at `http://rag-qdrant:6333`.
- `deploy/rag/.env.example` carries every key the code reads, with no value filled.
- `deploy/rag/Makefile` has `doctor`, `up`, `down`, `restart`, `rebuild`, `ps`, `logs`, and `doctor` fails on an empty required key.

## Non-goals

- Adding Qdrant, Mongo or any other data service to `common`. Mongo is there; Qdrant is local; that is [ADR-0009](../../../../adrs/9-rag-namespace.md).
- A data cutover from the old volumes. The stand starts empty.
- Publishing a port for debugging.

## Definition of Done

- [ ] `podman compose -f deploy/rag/docker-compose.yaml config` succeeds.
- [ ] `make doctor` fails with a non-zero exit when `MONGODB_URI`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` or `LLM_API_KEY` is empty.
- [ ] No service in the compose names `models_network`, `llm_network` or `rag_edge`.
- [ ] No service publishes a `ports:` entry.
- [ ] `rg 'models_network|llm_network|rag_edge|rag-mongo' deploy/rag` finds nothing.
