# rag-edge

The one HTTP entry of RAG. Listens on port `8080` and publishes no host port.

The container joins two networks:

- `rag_network` — the only RAG member. The auth gateway joins this network as external and proxies to `http://rag-edge:8080`; behind that edge the services may trust identity v1 headers.
- `rag_internal` — from here the edge reaches `file-collector`, `chat` and `frontend`.

## Routes

| Path | Where |
|------|------|
| `GET /health` | the edge's own answer: `{"status":"ok"}`. No identity header, no MongoDB, no queue. |
| `/api/files` and `/api/files/*` | `FILE_COLLECTOR_URL` |
| `/api/chats` and `/api/chats/*` | `CHAT_URL` |
| everything else | `FRONTEND_URL` |

An upload body passes through whole. The edge sets no limit stricter than `MAX_UPLOAD_BYTES`; `413` comes from File Collector.

A `text/event-stream` answer is not buffered: chat bytes go out as Chat sends them. Such an answer carries `X-Accel-Buffering: no`.

The incoming `X-Auth-Subject`, `X-Auth-Roles` and `X-Request-Id` go upstream. The edge does not verify them and does not mint a user: the gateway sets them. When `X-Request-Id` is absent or is not a UUID the edge creates a UUID, sends it upstream and returns it. Header set: [identity v1](../../../docs/auth-gateway/external-contracts/identity-v1.md).

## Variables

| Variable | Default |
|------------|----------------|
| `RAG_EDGE_PORT` | `8080` |
| `MAX_UPLOAD_BYTES` | `524288000` |
| `FILE_COLLECTOR_URL` | `http://file-collector:8081` |
| `CHAT_URL` | `http://chat:8082` |
| `FRONTEND_URL` | `http://frontend:3000` |
| `LOG_LEVEL` | `info` |

The default host names match the compose service names. A bad value stops the process; the log names the variable, never its value. Logs are JSON with `service` equal to `rag-edge`.

## Build

```sh
podman build -f Containerfile -t rag-edge .
```

`Dockerfile` matches `Containerfile`.

## Check

```sh
uv run ruff check
uv run ruff format --check
uv run pytest
```

Tests start local stubs and need no file-collector, chat or frontend.
