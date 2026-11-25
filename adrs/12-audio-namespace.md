# ADR-0012 The audio namespace moves in from ASR-Service

## Status

Accepted

## Decision

ASR-Service becomes a namespace of this repository: `audio`. One network, one env file, one compose file, per [ADR-0008](8-common-data-services.md) and [repository-layout.md](../docs/repository-layout.md).

| Fact | Value |
|---|---|
| Namespace | `audio` |
| Code | `src/audio/{audio-api,diarizer,asr-worker,frontend}` |
| Deploy | `deploy/audio/` |
| Docs | `docs/audio/` |
| Namespace network | `audio_network`, created here, `external: true` to the gateway |
| Host | `audio.filenkov.store`. Upstreams stay `audio-api:8000` and `frontend:80` |
| Role family | `svc:audio`, already `service(audio, family, admin)` on `/api/**` in the gateway config |
| Container names | `audio-<service>` |
| Compose service names | `audio-api`, `diarizer`, `asr-worker`, `frontend`, `qdrant` (DNS unchanged) |
| Mongo | the `common` server, database `audio`, reached as `mongo:27017` on `common_network` |
| MinIO | the `common` server, bucket `audio`, `minio:9000` |
| RabbitMQ, Redis | `rabbit:5672` and `redis:6379` on `common_network`. Redis holds the GPU lease |
| Qdrant | this namespace, container `audio-qdrant`, only on `audio_internal`. The volume starts empty |
| Hugging Face weights | a named volume in this namespace. It starts empty |
| Identity | `X-Auth-Subject` only, a canonical lower-case UUID. The gateway issuer is not changed |

The namespace joins three networks. `audio_network` is the gateway hop: `audio-api` and `frontend` join it, the gateway declares it `external: true`, and the upstream strings in the gateway config do not change. `audio_internal` is service-to-service: `audio-api`, `diarizer`, `asr-worker` and `qdrant`. It is not external. `common_network` carries Mongo, MinIO, RabbitMQ and Redis; `audio-api`, `diarizer` and `asr-worker` join it. `frontend` is only on `audio_network`. `qdrant` is only on `audio_internal`. No container publishes a host port.

There is no audio-edge proxy. The gateway already splits the host: `/health` and `/api/**` go to `audio-api:8000`, other paths go to `frontend:80`.

The existing Mongo database `audio` and the MinIO bucket `audio` stay. This story does not dump them and does not delete them. The new Qdrant storage volume and the new Hugging Face weight volume are created empty.

## Rejected

A second copy of the stack in a separate repository. A namespace named `asr`, which would keep the old product name. An audio-edge proxy in front of `audio-api` and `frontend`, which the gateway host block already splits. Qdrant on `common_network`, which would put one product's vector database on the shared network. Copying the old `qdrant_storage` or `hf_home` volumes into the new named volumes. A compatibility header set (`X-Auth-User-Id`, `X-Auth-Role`, `X-User-Id`, `X-Storage-Role`) beside identity v1, which [ADR-0001](1-one-contract-version.md) forbids.

## Cost

The stack lives in this repository, so its tests, lint and images become this repository's to keep green. `common` must be up before `audio`: Mongo, MinIO, RabbitMQ and Redis are four of its services. The old ASR-Service tree stays readable and is not deleted in this story; two trees for one product exist until a later deletion. Voice vectors and model weights are not copied, so the first GPU start downloads the weights again and `audio-api` creates the Qdrant collection on an empty volume. Recordings already in Mongo and MinIO are left in place.

## Risk

The identity contract the moved service reads is not the value this repository's edge writes today. ASR-Service reads `X-Auth-User-Id`. Identity v1 writes `X-Auth-Subject`. The move is a port onto that name. The subject must be a canonical lower-case UUID, the same external condition as [US-16](../docs/user_stories/us-16-rag-namespace/init.md) D6, because object keys are `u/{uuid}/` and Mongo stores that value as `owner_user_id`. The edge as it stands writes the Keycloak `sub`, which is not a UUID. This decision does not change the gateway issuer. Until the edge writes a UUID subject, `audio-api` answers `401` on every identified route. Workers do not read headers; they keep `owner_user_id` from the queue message.
