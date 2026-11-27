# ADR-0013 The llm namespace moves in from llama_proxy_lite and llama.cpp

## Status

Accepted

## Decision

The LiteLLM router and the llama.cpp server become a namespace of this repository: `llm`. One network, one env file, one compose file, per [ADR-0008](8-common-data-services.md) and [repository-layout.md](../docs/repository-layout.md).

| Fact | Value |
|---|---|
| Namespace | `llm` |
| Deploy | `deploy/llm/` |
| Docs | `docs/llm/` |
| Namespace network | none. Both services join `common_network`, declared `external: true` |
| Router container | `litellm-proxy-server`, image `ghcr.io/berriai/litellm:main-latest` |
| Server container | `qwen38`, image `ghcr.io/ggml-org/llama.cpp:server-cuda12` |
| DNS | `litellm-proxy-server:4000` and `qwen38:4001` on `common_network` |
| State | model file is the read-only bind `/media/aleksey/HardDisk/gguf_models:/models` |
| Database | the `common` Postgres, database `db_litellm`, reached as `postgres:5432` |
| Host publish | the router only, on `127.0.0.1:4000`, for the proxy's `lite-llm.filenkov.store` forward. The server publishes nothing. The gateway reaches both on `common_network` |
| Healthcheck | `curl -fsS http://127.0.0.1:4001/health` on `qwen38`, 120 s start period |

The two services were two ad-hoc scripts. LiteLLM ran from `~/projects/llama_proxy_lite/docker-compose.yaml` on `common_network` and `models_network`. llama.cpp ran from a `podman run` line in `~/projects/llama.cpp/startup_qwen3.8_work_instance_podman.sh` on `llm_network` only, `--replace`, with a host publish on `4001`. The router's `model_list` names `http://qwen38:4001`, so the name has to resolve from the router's own network set. It did not: `llm_network` is joined by neither the router nor the gateway, and every completion failed with `OpenAIException - Connection error` while both containers were healthy. The gateway joins `models_network` and reads the same `qwen38:4001` upstream, so the server has to be reachable from the router's side of the network set, not from a private bridge.

`common_network` is the one network both sides already share with the gateway's reachable set, and the database is there. The namespace therefore creates no network of its own; it declares `common_network` external and both services join it. No container publishes a host port other than the router's loopback `127.0.0.1:4000`, which is what the proxy's `lite-llm.` forward needs.

`LLM_API_KEY` is one value in `.env`, read by both services: llama.cpp takes it as `--api-key`, LiteLLM reads it through `os.environ/LLM_API_KEY`. The key does not live in `config.yaml`. `DATABASE_URL` and `LITELLM_MASTER_KEY` also move to `.env`.

## Rejected

Keeping `llm_network` and adding the router to it. The gateway does not join `llm_network`, so the public `llm.` upstream would still not resolve, and the private bridge would be a second path to the same server. Attaching the running server with `podman network connect` and leaving both manifests where they were, which fixes the symptom and leaves two trees for one product. Putting the server on `models_network`, which is Switch-Service's network and not this repository's to join ([ADR-0009](9-rag-namespace.md)). A host publish on `4001`, which exposes the API key-protected server to every interface. A wildcard publish of `4000` too: only the loopback address answers. Keeping the API key literal in `config.yaml`, which commits a credential.

## Cost

`common` must be up before `llm`: the router reads Postgres at start. The model file stays on the external disk, so the server fails to start when the disk is unmounted, the same condition the `common` MinIO service rejects. A 128k context start takes minutes; the healthcheck's 120 s start period is what keeps a slow load from marking the container unhealthy. The old `~/projects/llama_proxy_lite/` and the `startup_qwen3.8_work_instance_podman.sh` script are left in place and are not authoritative after this change.

## Risk

`llm_network` still exists on the host with no member. It is not removed here; a namespace that stops using a network does not delete it. `config.yaml` still names `qwen36:4002` for the `qwen3.6` model, and no container by that name runs, so that model group answers with a connection error until a `qwen36` server joins `common_network`. The router's `LITELLM_MASTER_KEY` is the value the old container ran with; clients that already hold it keep working.
