FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# This file is the deploy/<namespace>/<service>/Dockerfile of
# docs/repository-layout.md, and the service's Containerfile is the same file: it
# is built from the repository root, the only context that holds src/rag/common
# beside the service. The service pins rag-common at ../common, so the image
# mirrors the repository layout under /app: /app/src/rag/file-collector sits beside
# /app/src/rag/common.
WORKDIR /app/src/rag/file-collector

COPY src/rag/common/pyproject.toml /app/src/rag/common/pyproject.toml
COPY src/rag/common/src /app/src/rag/common/src
COPY src/rag/file-collector/pyproject.toml src/rag/file-collector/uv.lock src/rag/file-collector/README.md ./
COPY src/rag/file-collector/file_collector ./file_collector

RUN uv sync --frozen --no-dev --no-cache \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    FILE_COLLECTOR_PORT=8081

EXPOSE 8081

CMD ["/app/src/rag/file-collector/.venv/bin/python", "-m", "file_collector"]
