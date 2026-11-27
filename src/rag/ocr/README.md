# OCR

The internal single-page recognition service. The contract was `docs/openapi-internal.yaml` and the behaviour `docs/internal-services.md` in the legacy tree; the namespace entry is [docs/rag/init.md](../../../docs/rag/init.md). The service listens on `rag_internal` only. No host port is published.

## Model

`OCR_MODEL=surya-ocr-2`.

Engine: **Surya OCR 2** through **llama.cpp**, one model for English and Russian.

At process start, before the port opens, `surya-2.gguf` and `surya-2-mmproj.gguf` download from `datalab-to/surya-ocr-2-gguf` and `llama-server` starts at `127.0.0.1:8092`. That port never publishes to `rag_internal`. llama-server's thread count and memory ceiling are not set. Model reasoning stays off (`--reasoning off`): otherwise Qwen3.5 writes `<think>` until the page budget ends. A repeating tail stops generation at once, frees the slot, and the page does not wait for `OCR_TIMEOUT`.

While llama-server is unhealthy the process does not listen on `OCR_PORT` and readiness fails. After start, `GET /health` asks llama-server on every request: the weights and the CUDA context live there, so its death (including an OOM inside the container cgroup) shows as `503 dependency_unavailable`, not `ok`. A failed load ends the process. No GPU is required. The default image target is `cpu` (the pinned binary). The `cuda` target runs the same service on `ghcr.io/ggml-org/llama.cpp:server-cuda12`; `make up-gpu` builds it. The contract does not change.

`OCR_LLAMA_NGL` sets the mode — the `-ngl` flag value of llama-server: `-1` or `999` put all layers on GPU, `0` keeps pure CPU, an intermediate N offloads part of the layers. One image serves both modes; no rebuild. The default is `999`, as before, so existing deployments do not change; for the CPU target set `OCR_LLAMA_NGL=0`.

The service renders no page from the PDF. It expects the PNG Processor built. Another decodable raster is accepted. An unparseable body — `400` `validation_error`.

An empty `text` is a successful `200`, not an error.

## HTTP

`POST /ocr`, `multipart/form-data`, field `image`.

```json
{
  "text": "recognized text",
  "confidence": 0.92,
  "processing_time_ms": 340
}
```

`confidence` is a number from 0 to 1, or `null` when the engine gave no estimate. `processing_time_ms` is engine time, an integer ≥ 0.

The parse budget is `OCR_TIMEOUT` seconds (120). At the deadline the service answers `504`:

```json
{"error": {"code": "upstream_timeout", "message": "OCR timed out"}}
```

`GET /health` → `{"status":"ok"}` while llama-server answers. Otherwise `503`:

```json
{"error": {"code": "dependency_unavailable", "message": "Model is not loaded"}}
```

A `503` means the next `POST /ocr` would return `500`; a container restart through Switch-Service brings the service back.

An optional `X-Request-Id` header (UUID) returns in the answer. Absent or non-UUID, the service substitutes a new UUID.

## Variables

| Variable | Default | Meaning |
|------------|--------------|--------|
| `OCR_PORT` | `8090` | Port inside the network. |
| `OCR_MODEL` | `surya-ocr-2` | Surya OCR 2. Any other value stops the start. |
| `OCR_TIMEOUT` | `120` | Seconds for one parse. |
| `OCR_LLAMA_URL` | `http://127.0.0.1:8092` | llama-server inside the container. |
| `OCR_LLAMA_NGL` | `999` | Layers on GPU: `-1`/`999` — all, `0` — CPU. Allowed `-1..999`. |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error`. |

A bad value logs only the variable name.

## Run

From this directory:

```bash
uv sync
uv run python -m ocr_service
```

Image (no outward port forward):

```bash
podman build -f Dockerfile --target cpu -t ocr .
podman build -f Dockerfile --target cuda -t ocr:cuda .
```

## Tests

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

Tests substitute a fake page reader and download no weights. The real entry `python -m ocr_service` starts `llama-server` with `surya-2.gguf` and `surya-2-mmproj.gguf`.
