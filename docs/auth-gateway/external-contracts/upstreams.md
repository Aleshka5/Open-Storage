# Product resources

Applications outside this namespace. Gateway reaches them by the upstream name. They receive [identity v1](identity-v1.md) when the route is authorized.

| Resource | Upstream | Host | Policy |
|---|---|---|---|
| storage | `app:8000` | `storage.filenkov.store` | `service(storage, family, admin)` except `/health` |
| image | `qwen-image:8000` | `image.filenkov.store` | `service(image, family, admin)` except `/healthz` |
| rag | `rag-edge:8080` | `rag.filenkov.store` | `service(rag, family, admin)` except `/health` |
| audio API | `audio-api:8000` | `audio.filenkov.store` `/api/**` and `/health` | service role, health public |
| audio UI | `frontend:80` | `audio.filenkov.store` other paths | `session` |
| llm | `qwen38:4001` | `llm.filenkov.store` | `admin` |
| observer | `grafana:3000` | `observer.filenkov.store` | `session`, plus Grafana's own login. `/api/health` public |
| meet | `jitsi-web:8000` in gateway config; the Caddyfile sends the name to `127.0.0.1:8000` | `meet.filenkov.store` | Gateway config says `session`. The proxy never sends the request there. LAN / WireGuard gate is in Caddy. |
| switch | `192.168.1.102:8095` (LAN address; `host.docker.internal` does not answer under rootless podman) | `filenkov.store` `/api/services` | `GET` is `session`, the rest is `admin`. Gateway injects `X-Service-Token`. |
| litellm | `litellm-proxy-server:4000` | none | Declared in `upstreams`. No route names it. `POST /api/chat` is the in-process owl (`llm:` block), not this upstream. |

`hermes.filenkov.store` and `lite-llm.filenkov.store` are not in this table. Proxy forwards them to local ports. They keep their own authentication.

Consumers that still read `X-User-Id`, `X-Storage-Role`, `X-Auth-User-Id`, or `X-Auth-Role` have to move to v1 in the same release as this namespace. Known consumers: WebStorage, RAG-Chat, ASR-Service, qwen-image-service. Switch-Service already takes `X-Service-Token` from the edge.
