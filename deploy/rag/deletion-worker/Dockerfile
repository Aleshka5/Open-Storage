FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# This file is the deploy/<namespace>/<service>/Dockerfile of
# docs/repository-layout.md, and the service's Containerfile is the same file: it
# is built from the repository root, the only context that holds src/rag/common
# beside the service. The service pins rag-common at ../common, so the image
# mirrors the repository layout under /app: /app/src/rag/deletion-worker sits beside
# /app/src/rag/common.
WORKDIR /app/src/rag/deletion-worker

COPY src/rag/common/pyproject.toml /app/src/rag/common/pyproject.toml
COPY src/rag/common/src /app/src/rag/common/src
COPY src/rag/deletion-worker/pyproject.toml src/rag/deletion-worker/uv.lock src/rag/deletion-worker/README.md ./
COPY src/rag/deletion-worker/deletion_worker ./deletion_worker

RUN uv sync --frozen --no-dev

USER nobody
CMD ["/app/src/rag/deletion-worker/.venv/bin/python", "-m", "deletion_worker"]
