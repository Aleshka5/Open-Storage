# Embedding

The internal vector service for RAG Chat. Listens on `POST /embed`, `POST /embed/image` and `GET /health` inside `rag_internal`. No host port is published.

Norm: `docs/openapi-internal.yaml`, `docs/internal-services.md`, `docs/configuration.md` in the legacy tree; this namespace's entry is [docs/rag/init.md](../../../docs/rag/init.md).

The model in the answer is `google/embeddinggemma-2`. A vector is 768 numbers after mean pooling and L2 normalization. No truncation to 512, 256 or 128 exists.

`llama-server` from llama.cpp (architecture `gemma-embedding2`) computes the vector at `127.0.0.1:8092`. FastAPI at `EMBEDDING_PORT` (8091) attaches the prefix and validates the vector. Only FastAPI is visible on the application network. PyTorch and `model.safetensors` are not used. F16 is not loaded. The image projector `mmproj-embeddinggemma-2-Q8_0.gguf` (`EMBEDDING_MMPROJ`) is passed to `llama-server` with `--mmproj`. No separate audio projector loads.

Default weights: `ggml-org/embeddinggemma-2-GGUF`, file `embeddinggemma-2-Q8_0.gguf`. Tokens count with the `tokenizer.json` of the `google/embeddinggemma-2` revision recorded in that GGUF's `.src_sha` (`914f7f89142e33e77833254d9c9b90c3cef7303b`). The count includes the `<bos>` and `<eos>` from that file's post-processor.

## Prefixes

One `input_type` per batch.

| `input_type` | String for the model |
|--------------|-------------------|
| `query` | `task: question answering \| query: {text}` |
| `document` | `title: {title} \| text: {text}` |

`title` is the file name. Required for `document`, forbidden for `query`, including empty and `null`. `texts` and `title` edges are stripped; an empty string after `strip` — `400 validation_error`. The service trims no text itself: if tokens after the prefix exceed `EMBEDDING_MAX_TOKENS` (1024), the answer is `400`.

A batch is 1 to `EMBEDDING_BATCH_SIZE` texts, 16 by default. A `model` field, when sent, must equal `EMBEDDING_MODEL`.

`embeddings[i]` matches `texts[i]`. A length other than `EMBEDDING_DIM`, NaN, infinity, or a zero norm — `502 upstream_failed`. When the norm is not 1, the service normalizes itself. A batch timeout — `504 upstream_timeout`.

## Images

`POST /embed/image` computes an image vector in the same 768 space. The body is `images`: a base64 array of 1 to `EMBEDDING_MAX_IMAGES` (4). The optional `model` field behaves as in `/embed`. Fields `texts`, `input_type` and `title` give `400 validation_error`: an image has no task prefix.

A container is accepted only by signature: JPEG (`FF D8 FF`), PNG (`89 50 4E 47 0D 0A 1A 0A`), GIF (`GIF87a` / `GIF89a`), WebP (`RIFF` plus `WEBP` at offset 8). Anything else, bad base64, and a decoded size above `EMBEDDING_MAX_IMAGE_BYTES` (10485760) — `400`, field `images`. A signature accepted but llama-server fails to decode the file, answers with an error, or the image projector is not loaded — `502 upstream_failed`. Timeout — `504 upstream_timeout`. `POST /embed` and `GET /health` stay available without the projector. When several of `texts`, `input_type`, `title` were sent, `details.fields` names each.

`POST /v1/embeddings` takes the batch without text. Each `input` element holds one `content` block with an `image_url` part and the data URI `data:image/<type>;base64,<base64>`. Beside it `encoding_format` equals `float`. The answer matches `/embed`: `embeddings[i]` corresponds to `images[i]`, the same L2 projection.

`GET /health` answers `200` with `{"status":"ok"}` only after the GGUF loads. A failed load stops the process. An optional `X-Request-Id` (UUID) is returned; otherwise a new UUID is issued.

## Variables

| Variable | Default |
|------------|----------------|
| `EMBEDDING_PORT` | `8091` |
| `EMBEDDING_MODEL` | `google/embeddinggemma-2` |
| `EMBEDDING_GGUF` | `embeddinggemma-2-Q8_0.gguf` |
| `EMBEDDING_LLAMA_URL` | `http://127.0.0.1:8092` |
| `EMBEDDING_CONTEXT` | `2048` |
| `EMBEDDING_DIM` | `768` |
| `EMBEDDING_MAX_TOKENS` | `1024` |
| `EMBEDDING_BATCH_SIZE` | `16` |
| `EMBEDDING_MAX_IMAGES` | `4` |
| `EMBEDDING_MAX_IMAGE_BYTES` | `10485760` |
| `EMBEDDING_MMPROJ` | `mmproj-embeddinggemma-2-Q8_0.gguf` |
| `EMBEDDING_TIMEOUT` | `30` |
| `EMBEDDING_LLAMA_NGL` | `999` |
| `LOG_LEVEL` | `info` |

`EMBEDDING_LLAMA_NGL` goes to `llama-server` as `-ngl`: how many layers run on GPU. `999` (default) is all layers, `-1` means the same in llama.cpp terms, `0` is CPU only. The allowed range is `-1..999`; any other value stops the process from starting. On the CPU image build the flag changes nothing: the non-CUDA binary ignores it.

`EMBEDDING_LLAMA_URL` stays on `127.0.0.1` or `localhost`. A bad value stops the start; the log names the variable, never its value. `EMBEDDING_CONTEXT`, `--batch-size` and `--ubatch-size` are equal. llama-server's `--parallel` is 1. The container memory budget is about 2 GiB.

## Run and check

Dependencies install through `uv`, not pip. `uv.lock` pins versions. `requirements.txt` is the same list for reading.

```bash
cd src/rag/embedding
uv sync --group dev
uv run ruff check
uv run ruff format --check
uv run pytest
```

The image builds with Podman from `Containerfile` (the same text as `Dockerfile`). The file has two targets: `cpu` (also `default`, a build without `--target`) and `cuda`:

```bash
# CPU, the default
podman build -f Containerfile -t embedding .
# GPU: the same service on ghcr.io/ggml-org/llama.cpp:server-cuda12
podman build -f Containerfile --target cuda -t embedding:gpu .
```

In the `cuda` build, `llama-server` and the ggml libraries from `/app` of the base image move to `/opt/llama` (`libcudart` and `libcublas` from the CUDA runtime stay there), `LLAMA_ARG_HOST`/`LLAMA_ARG_PORT` are overridden to `127.0.0.1:8092`, and Python is the system one (`UV_PYTHON=python3`). GPU layers are set by `EMBEDDING_LLAMA_NGL`.

The image runs two processes: `llama-server` on `127.0.0.1:8092` only, and `python -m embedding` on 8091. Port 8092 never opens outward; compose publishes no host port for 8091. The first request waits for no weight download: loading finishes before `/health` turns ready.

Tests call a stub encoder and download no GGUF. The real entry `python -m embedding` runs `load_model`: it downloads the text Q8_0 and `mmproj-embeddinggemma-2-Q8_0.gguf`, starts `llama-server --embeddings --pooling mean --mmproj`, and waits for its `/health`. Without the projector file the process still starts; `POST /embed/image` answers `502`.
