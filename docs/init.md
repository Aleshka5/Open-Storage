# System

One namespace is one block. A link is an action the block requests, or a resource it uses.

## Namespaces

| Namespace | Block | Deploy | Code |
|---|---|---|---|
| auth-gateway | Identity and edge for `*.filenkov.store` | `deploy/auth-gateway/` | `src/auth-gateway/` |

Detail inside the block: [auth-gateway/init.md](auth-gateway/init.md).

## What auth-gateway requests

| Link | Kind | Resource or action |
|---|---|---|
| Google | action | Sign the user in. Redirect URI: `https://id.filenkov.store/realms/filenkov/broker/google/endpoint` |
| storage | resource | `app:8000` — files |
| image | resource | `qwen-image:8000` — image generation |
| rag | resource | `rag-edge:8080` — chat and documents |
| audio | resource | `audio-api:8000` and `frontend:80` |
| llm | resource | `qwen38:4001` |
| observer | resource | `grafana:3000` |
| meet | resource | `jitsi-web:8000` |
| switch | resource | `host.docker.internal:8095` — model switching |
| litellm | resource | `litellm-proxy-server:4000` — showcase chat |

`hermes` (`127.0.0.1:9119`) and `lite-llm` (`127.0.0.1:4000`) are not part of this SSO contract. The proxy forwards them and auth-gateway does not authenticate them.

Product applications are outside this repository. The headers they receive are [auth-gateway/external-contracts/identity-v1.md](auth-gateway/external-contracts/identity-v1.md).

## Hosts on the block

SSO hosts, one upstream each, all into auth-gateway: `filenkov.store`, `storage.`, `image.`, `rag.`, `audio.`, `llm.`, `observer.`, `meet.`, `id.`.

`meet.filenkov.store` is LAN and WireGuard only. `hermes.filenkov.store` is outside SSO and LAN and WireGuard only.
