# Dockerfile diarizer (Python 3.12, uv, CUDA-compatible torch).
# US-02: the real worker. ffmpeg is needed for normalization (ADR-014); model weights live in
# the HF_HOME volume (ADR-013), not in the image.
FROM python:3.12-slim

WORKDIR /srv

# ffmpeg — decoding into norm.wav (16 kHz mono s16le).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra gpu

COPY app ./app

ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000

# Call the venv directly. `uv run` syncs the dev group on every start and
# reaches PyPI; a fresh container then crash-loops when that fetch fails,
# and audio-api never starts (the gateway answers 502).
CMD ["/srv/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
