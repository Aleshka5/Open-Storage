# rag — external contract

What the namespace requires from systems outside itself. One row per call. "Contract" is what the other side must keep true for this namespace to work; the linked document owns the fact.

Every service trusts identity because its only inbound path is the gateway on `rag_network`, or a caller inside `rag_internal`. No service verifies a JWT, sets a response header the gateway already sets, or reads a cookie.

## auth-gateway

| External system | Call | Used for | Contract it must satisfy |
|---|---|---|---|
| gateway | Inbound: any request to `rag.filenkov.store`, proxied to `rag-edge:8080` | Every request the product serves | Header set and strip list: [identity v1](../auth-gateway/external-contracts/identity-v1.md). Host, upstream, policy, timeout: [upstreams](../auth-gateway/external-contracts/upstreams.md), gateway `config.yaml` |
| gateway → services | `X-Auth-Subject` | The user key. Every Mongo document field `user_id`, every Qdrant point payload `user_id`, every `rag_internal` hop | A canonical lower-case UUID, stable per person. This is the condition in [US-16](../user_stories/us-16-rag-namespace/init.md) D6. The gateway forwards the token `sub` unchanged, so the condition is the idp's to keep: a realm built from `src/auth-gateway/idp/realm.json` issues UUID subjects |
| gateway → services | `X-Auth-Roles` | Role family: `svc:rag:blocked` denies with `403`, `svc:rag:admin` and `svc:rag:family` pass, empty means the edge already refused | Realm roles only, per [idp roles](../auth-gateway/idp/init.md) |
| gateway → services | `X-Auth-Email`, `X-Auth-Name`, `X-Auth-Session` | Not read | — |
| gateway → services | `Authorization: Bearer ***` | Not read | — |
| rag-edge → client | `X-Request-Id` | Traced through `rag_internal` to the service that answered | Absent or non-UUID on arrival means the edge generates one and returns it |

The edge answers its own errors `{"error":{"code","message"}}`; the services answer the same shape. The gateway answers `{"error":"unauthorized"}` on its own refusals, before `rag-edge` is reached.

## common

| Call | Used for | Contract |
|---|---|---|
| Mongo over `MONGODB_URI`, `mongo:27017`, database `rag` | Documents, chunks, chats, messages | The [common](../common/init.md) server; one database per product; no auth on the server today |
| `S3_ENDPOINT` `http://minio:9000`, bucket `storage`, path style | The uploaded object every service reads | Bucket `storage` shared with [open-storage](../open-storage/init.md): storage writes the user's files, rag reads keys it is given and writes nothing under `users/` itself |
| `RABBITMQ_URL` `amqp://rabbit:5672/`, exchange `doc_events`, DLX `doc_events_dlq` | The `doc.processing` and `doc.delete` work queues, prefetch 1 | [common](../common/init.md); `rabbit` is the alias of `rabbitmq` |

## models

| Call | Used for | Contract |
|---|---|---|
| `POST {LLM_BASE_URL}/chat/completions`, OpenAI-compatible | The answer in `chat` | Streams SSE deltas; a `429` is retried, other `4xx` ends the turn without saving a pair. `LLM_BASE_URL` is the LiteLLM router, `http://litellm-proxy-server:4000/v1` on `common_network` ([llm/init.md](../llm/init.md)); provider keys live at the router. No `llm_network` |
| `POST ocr:8090/ocr` | Text from a rendered scan page | One image per call, `OCR_TIMEOUT` (120 s) |
| `POST embedding:8091/embed`, `POST embedding:8091/embed/image` | Chunk and image vectors | Batch 16, dimension 768, `EMBEDDING_TIMEOUT` (30 s). `sha256` and the batch shape are the contracts in the old tree's `docs/internal-services.md` |

## Network reach

| Call | Network |
|---|---|
| gateway → `rag-edge:8080` | `rag_network`, created by this namespace and declared external, by that name, by the gateway |
| edge → `file-collector:8081`, `chat:8082`, `frontend:3000` | `rag_internal` |
| file-collector, processor, deletion-worker, chat → `mongo`, `minio`, `rabbit` | `common_network` |
| processor, deletion-worker, chat → `rag-qdrant:6333` | `rag_internal` |
| processor → `embedding:8091`, `ocr:8090` | `rag_internal` |
| chat → the model URL | egress, no bridge |
