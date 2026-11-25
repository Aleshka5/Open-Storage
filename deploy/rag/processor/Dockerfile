FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZER_JSON=/app/tokenizer/tokenizer.json

# This file is the deploy/<namespace>/<service>/Dockerfile of
# docs/repository-layout.md, and the service's Containerfile is the same file: it
# is built from the repository root, the only context that holds src/rag/common
# beside the service. The service pins rag-common at ../common, so the image
# mirrors the repository layout under /app: /app/src/rag/processor sits beside
# /app/src/rag/common.
WORKDIR /app/src/rag/processor

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin processor

COPY src/rag/common/pyproject.toml /app/src/rag/common/pyproject.toml
COPY src/rag/common/src /app/src/rag/common/src
COPY src/rag/processor/pyproject.toml src/rag/processor/uv.lock src/rag/processor/README.md ./
COPY src/rag/processor/src ./src

RUN uv sync --frozen --no-dev \
    && mkdir -p /app/tokenizer \
    && /app/src/rag/processor/.venv/bin/python -c "from huggingface_hub import hf_hub_download; import shutil; p=hf_hub_download('google/embeddinggemma-2','tokenizer.json',revision='914f7f89142e33e77833254d9c9b90c3cef7303b'); shutil.copy(p,'/app/tokenizer/tokenizer.json')" \
    && chown -R processor:processor /app

USER processor
CMD ["/app/src/rag/processor/.venv/bin/python", "-m", "processor"]
