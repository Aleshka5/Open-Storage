"""Service configuration — the single source of secrets.

Secrets come only through `get_settings()` (constitution.md §10). `audio-api` never receives
`HF_TOKEN` in any form.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # S3 (MinIO)
    s3_endpoint_url: str = "http://minio:9000"
    s3_bucket: str = "audio"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_use_path_style: bool = True

    # Mongo
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "audio"
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_max_pool_size: int = 20

    # Qdrant
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "audio_voices"
    suggestion_limit: int = 5
    # Voice vector dimension — set by the diarization embedding model
    # (diarizer: CENTROID_DIM = 256). This is a contract constant, not a "for the future" toggle.
    voice_embedding_size: int = 256

    # RabbitMQ
    rabbitmq_url: str = ""
    rabbitmq_prefetch: int = 20
    rabbitmq_retry_ttl_ms: int = 30000
    rabbitmq_max_attempts: int = 3

    # audio-api
    asr_stream_url: str = "ws://asr-worker:8020/v1/stream"
    max_upload_bytes: int = 2147483648  # 2 GiB
    processing_stall_seconds: int = 900
    poll_hint_ms: int = 1500
    # Voluntary phrase polling budget, requests/min per owner (US-08).
    # `0` — disabled: the limit is held by the gateway (ADR-005). The value is not above 180.
    poll_budget_per_minute: int = 0

    # Note codec (ADR-012 §6): PCM → WebM/Opus is muxed by ffmpeg on the fly.
    ffmpeg_path: str = "ffmpeg"

    # Minimum voice duration for embedding (queue-audio-embedding/message.md):
    # a shorter note — no vector is built, `embedding.failed (too_short)` and
    # `409 VOICE_NOT_READY` on `PUT /api/me/voice`. The technical value is the same as
    # `MIN_EMBED_SECONDS` in diarizer: the value is derived from `voice_embedding_min_ms`.
    voice_embedding_min_ms: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
