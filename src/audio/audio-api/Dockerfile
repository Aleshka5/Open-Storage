# Dockerfile audio-api (Python 3.12, uv).
FROM python:3.12-slim

WORKDIR /srv

# ffmpeg: ffprobe for media validation on upload + on-the-fly PCM → WebM/Opus muxing
# for the voice note (ADR-012 §6). Without it: `MUXER_UNAVAILABLE`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# End-to-end smoke scenario (US-08): `make smoke` runs it inside the container —
# `websockets` from `uvicorn[standard]` is available here, plus a direct path to asr-worker.
COPY smoke.py ./smoke.py

ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8000

# Call the venv directly. `uv run` syncs the dev group on every start and
# reaches PyPI; a fresh container then exits when that fetch fails.
CMD ["/srv/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
