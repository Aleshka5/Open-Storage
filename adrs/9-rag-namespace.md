# ADR-0009 The rag namespace moves in from RAG-Chat

## Status

Accepted

## Decision

RAG-Chat becomes a namespace of this repository: `rag`. One network, one env file, one compose file, per [ADR-0008](8-common-data-services.md) and [repository-layout.md](../docs/repository-layout.md).

| Fact | Value |
|---|---|
| Namespace | `rag` |
| Code | `src/rag/{rag-edge,file-collector,processor,deletion-worker,chat,frontend,embedding}` |
| Deploy | `deploy/rag/` |
| Docs | `docs/rag/` |
| Namespace network | `rag_network`, created here, `external: true` to the gateway |
| Host | `rag.filenkov.store`, upstream `rag-edge:8080` |
| Role family | `svc:rag:{admin,family,blocked}`, already in `realm.json` |
| Container names | `rag-<service>`, no bare product word |
| Mongo | the `common` server, database `rag`, reached as `mongo:27017` on `common_network` |
| Qdrant | this namespace, its own container `rag-qdrant` on `rag_network` |
| OCR, embedding | this namespace, on `rag_internal`; no `models_network` |
| MinIO, RabbitMQ | the `common` services, `minio:9000` and `rabbit:5672` on `common_network` |

The namespace joins three networks: `rag_network` (edge hop, `external: true`, the gateway reaches `rag-edge:8080` there), `common_network` (MinIO `minio:9000`, RabbitMQ `rabbit:5672`, Mongo `mongo:27017`), and `rag_internal` (service-to-service inside the stack, not external). `rag_network` is created here and declared external by the gateway, mirroring how `rag_edge` works today. `models_network` is not joined: OCR and embedding move in, so the stack no longer reaches Switch-Service. `llm_network` is not joined either; the LLM base URL is env, not a bridge.

## Rejected

A second copy of the stack in a separate repository. A namespace named `rag-chat`, which would preserve a product name that the move retires. Keeping `rag_internal` as the only network, which the gateway cannot reach. Keeping the RAG-owned `rag-mongo` alias, which collides with `common`'s `mongo`. Qdrant in `common`, which would put a vector database on the shared network for one product. OCR and embedding on `models_network`, which is Switch-Service's network and not this repository's to join. Renaming the source repository in place, which loses the old tree as a reference during the cutover.

## Cost

The stack lives in this repository, so its tests, lint and images become this repository's to keep green. `common` must be up before `rag`: Mongo, MinIO and RabbitMQ are three of its services. The old RAG-Chat repository stays readable but not developed until the stand is accepted, then it is deleted; two trees for one product exist in between. The in-progress `common` work was uncommitted on a detached HEAD when this branch was cut; it is carried in as its own commit rather than rebuilt.

## Risk

The identity contract the moved services read is not the one this repository's edge writes. RAG-Chat reads `X-Auth-User-Id` and `X-Auth-Role`; identity v1 writes `X-Auth-Subject` and `X-Auth-Roles`. The move is not a copy: it is a port onto v1, and until that port lands the services answer `401` on every route. The subject is also not the UUID that RAG stores as `user_id`, so the port needs either a stable UUID from the edge or a key migration. Both are recorded in [US-16](../docs/user_stories/us-16-rag-namespace/init.md) and are not decided here.
