# Dockerfile asr-worker (Python 3.12, uv, CUDA-compatible torch).
# US-03: the real transcription worker. Parakeet weights live in the HF_HOME volume (ADR-013),
# not in the image. ffmpeg is not needed: the input is already normalized norm.wav (ADR-014).
FROM python:3.12-slim

WORKDIR /srv

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra gpu

COPY app ./app

ENV PATH="/srv/.venv/bin:$PATH"

EXPOSE 8020

# `--ws websockets-sansio` is mandatory: with the default (`auto` -> the legacy
# `websockets` implementation) uvicorn 0.54 + websockets 17.4 accepts the TCP connection
# and then never answers the upgrade — every `/v1/stream` handshake hung until the client
# timed out and the note socket answered ASR_UNAVAILABLE (verified on the stand
# 2026-11-01: 101 Switching Protocols with this flag, silence without it).
# Call the venv directly. `uv run` syncs the dev group on every start and
# reaches PyPI; a fresh container then crash-loops when that fetch fails,
# and audio-api never starts (the gateway answers 502).
CMD ["/srv/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020", "--ws", "websockets-sansio"]
