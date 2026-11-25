> **ID:** US-18 task-02
> **Status:** REVIEW
> **Specs:** [ADR-0012](../../../../adrs/12-audio-namespace.md), [common](../../../common/init.md), [US-18](../init.md)

## Overview

`deploy/audio/` is a new compose, not a copy of `../ASR-Service/deploy/docker-compose.yml`. Service DNS names stay so the gateway upstream strings do not change. Container names take the `audio-` prefix. Qdrant leaves `common_network`. Volumes for Qdrant and Hugging Face weights are new and empty.

## Goals

- `deploy/audio/docker-compose.yaml` defines `audio-api`, `diarizer`, `asr-worker`, `frontend` and `qdrant`.
- Container names: `audio-audio-api`, `audio-diarizer`, `audio-asr-worker`, `audio-frontend`, `audio-qdrant`.
- Networks: `audio_network` (created here), `audio_internal`, `common_network` (`external: true`).
- `qdrant` joins only `audio_internal`. `frontend` joins only `audio_network`. `audio-api` joins `audio_network`, `audio_internal` and `common_network`. `diarizer` and `asr-worker` join `audio_internal` and `common_network`.
- DNS inside the stack: `audio-api:8000`, `frontend:80`, `asr-worker:8020`, `qdrant:6333`.
- Data names: `mongodb://mongo:27017` database `audio`, `http://minio:9000` bucket `audio`, `amqp://rabbit:5672/`, `redis://redis:6379`, `http://qdrant:6333`.
- Named volumes for Qdrant storage and Hugging Face weights, with no external volume and no bind of the old data.
- No `ports:` entry.
- `deploy/audio/.env.example` lists the keys with empty required secrets. No `minioadmin`, no `guest:guest`.
- `deploy/audio/Makefile` has `doctor`, `up`, `down`, `restart`, `rebuild`, `ps`, `logs`. `doctor` fails when a required key is empty.
- Secrets only through `deploy/audio/.env`.

## Non-goals

- Publishing a host port.
- Copying `qdrant_storage` or `hf_home` from the old stand.
- Dumping or deleting the Mongo database `audio` or the MinIO bucket `audio`.
- Starting the GPU stack.

## Definition of Done

- [ ] `podman compose -f deploy/audio/docker-compose.yaml config` succeeds. Not run: `podman` is not installed. `docker compose config` succeeds and the rendered file matches the network and volume rules below.
- [x] `make doctor` fails with a non-zero exit when a required key is empty.
- [x] No service publishes a `ports:` entry.
- [x] `qdrant` is not on `common_network` or `audio_network`.
- [x] `.env.example` contains no `minioadmin` and no `guest:guest`.
