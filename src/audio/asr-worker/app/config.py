"""asr-worker configuration — the single source of secrets.

Secrets come only through `get_settings()` (constitution §10). `HF_TOKEN` is not needed here
(Parakeet is an open model) but is kept for symmetry with the models/hf.md contract.
Secrets never reach logs or other services.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Model
    hf_token: str | None = None
    hf_home: str = "/models/hf"
    asr_model: str = "nvidia/parakeet-tdt-0.6b-v3"
    asr_revision: str = "541d1f99c6b0c3cd0b11a95167540bb8edefd82b"
    device: str = "cuda"
    allow_cpu_models: bool = False

    # GPU lease (Redis)
    gpu_lease_url: str = "redis://redis:6379"
    gpu_lease_ttl_ms: int = 30000
    gpu_lease_heartbeat_ms: int = 5000

    # Offline batch (ADR-014 / asr-worker S-04)
    batch_max_turns: int = 8
    batch_max_seconds: int = 60
    # Windows per GPU call (S-07). Not the chat cadence: a batch still emits one progress
    # event, this only decides how many of its windows share one forward pass.
    asr_gpu_batch_size: int = 8

    # Stream (US-05; contract constants, changed by ADR)
    stream_left_s: int = 10
    stream_chunk_s: int = 2
    stream_right_s: int = 2
    max_stream_sessions: int = 1
    stream_url_bind: str = "0.0.0.0:8020"

    # Scratch
    scratch_dir: str = "/tmp/audio"
    scratch_cleanup_minutes: int = 120

    # Mongo
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "audio"

    # RabbitMQ
    rabbitmq_url: str = "amqp://rabbit:5672/"
    rabbitmq_prefetch: int = 1
    rabbitmq_max_attempts: int = 3

    # S3 (MinIO)
    s3_endpoint_url: str = "http://minio:9000"
    s3_bucket: str = "audio"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_use_path_style: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
