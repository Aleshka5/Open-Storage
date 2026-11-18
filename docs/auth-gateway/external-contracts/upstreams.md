# Product resources

Applications outside this namespace. Gateway reaches them by the upstream name. They receive [identity v1](identity-v1.md) when the route is authorized.

| Resource | Upstream | Host | Policy |
|---|---|---|---|
| storage | `app:8000` | `storage.filenkov.store` | `service(storage, family, admin)` except `/health` |
| image | `qwen-image:8000` | `image.filenkov.store` | `service(image, family, admin)` except `/healthz` |
| rag | `rag-edge:8080` | `rag.filenkov.store` | `service(rag, family, admin)` except `/health` |
| audio API | `audio-api:8000` | `audio.filenkov.store` `/api/**` and `/health` | service role, health public |
| audio UI | `frontend:80` | `audio.filenkov.store` other paths | policy not set — see [init.md](../init.md) |
| llm | `qwen38:4001` | `llm.filenkov.store` | `admin` |
| observer | `grafana:3000` | `observer.filenkov.store` | `session`, plus Grafana's own login. `/api/health` public |
| meet | `jitsi-web:8000` | `meet.filenkov.store` | `session`, and proxy allows LAN / WireGuard only |
| switch | `host.docker.internal:8095` | `filenkov.store` `/api/services` | `GET` is `session`, the rest is `admin`. Gateway injects `X-Service-Token`. |
| litellm | `litellm-proxy-server:4000` | `filenkov.store` `POST /api/chat` | `public`. Gateway injects `X-Api-Key`. |

`hermes.filenkov.store` and `lite-llm.filenkov.store` are not in this table. Proxy forwards them to local ports. They keep their own authentication.

Consumers that still read `X-User-Id`, `X-Storage-Role`, `X-Auth-User-Id`, or `X-Auth-Role` have to move to v1 in the same release as this namespace. Known consumers: WebStorage, RAG-Chat, ASR-Service, qwen-image-service. Switch-Service already takes `X-Service-Token` from the edge.
