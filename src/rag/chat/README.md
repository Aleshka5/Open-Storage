# Chat

HTTP service for `/api/chats`. It stores chats in MongoDB, embeds the question, searches Qdrant by `user_id`, and streams an answer from an OpenAI-compatible LLM.

The process listens on `CHAT_PORT` (default `8082`).

## Run

Required environment variables have no defaults: `MONGODB_URI`, `QDRANT_URL`, `EMBEDDING_URL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Optional variables and their defaults are in `docs/configuration.md`.

```bash
python -m chat
```

`GET /health` returns `{"status":"ok"}` and does not check dependencies. Every other route requires `X-Auth-Subject` as a canonical UUID; `X-Auth-Roles` is a space-separated realm-role list and the exact token `svc:rag:blocked` returns 403. The pre-v1 headers `X-Auth-User-Id`, `X-Auth-Role` and `X-User-Id` are not read. Header set: [identity v1](../../../docs/auth-gateway/external-contracts/identity-v1.md).

`POST /api/chats/{chat_id}/messages` responds with `text/event-stream`: `meta`, then `delta`, then `done`. The `meta` event carries the sources that are stored on the assistant message.

## Tests

From this directory:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

The tests use an in-memory Mongo stand-in, an in-memory Qdrant stand-in, and HTTP fakes for the embedding service and a token-streaming LLM. They do not call the network.

## Image

From this directory:

```bash
podman build -t chat -f Dockerfile .
```
