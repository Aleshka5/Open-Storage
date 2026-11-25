"""diarizer — GPU worker: diarizes uploads from `audio.diarization`.

`/health` answers `503` until the model is loaded (ADR-013: no silent fallback).
The model loads at startup (fp16 on CUDA); the queue consumer runs in a separate thread.
There is no public HTTP besides `/health` (api.md). A model load failure means a crash at
startup (hf_auth_failed), not a half-started service.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.application.diarize import ACK, NACK_RETRY, RETRY_WITH_ATTEMPT, DiarizationHandler
from app.application.embed import EmbeddingHandler
from app.application.ports.diarizer_model import ModelLoadError
from app.application.ports.json_queue import QUEUE_DIARIZATION, QUEUE_EMBEDDING
from app.config import Settings, get_settings
from app.infrastructure.gpu_lease import RedisGpuLease
from app.infrastructure.minio_store import S3ObjectStore
from app.infrastructure.mongo import MongoSpeakerRepo
from app.infrastructure.normalizers import NormalizerAdapter
from app.infrastructure.pyannote_embedding import PyannoteEmbedder
from app.infrastructure.pyannote_model import PyannoteDiarizer
from app.infrastructure.rabbitmq import (
    QUEUE_EVENTS,
    QUEUE_TRANSCRIPTION,
    RabbitMQQueue,
)
from app.logging import install as install_logging

logger = logging.getLogger(__name__)


class WorkerState:
    def __init__(self) -> None:
        self.model: object = None
        self.loaded: bool = False
        self.gpu_ok: bool = True
        self.embedding_loaded: bool = False


_state = WorkerState()


def _startup_scratch_cleanup(scratch_dir: str, minutes: int) -> None:
    """Frees space after a crash: `find … -mmin +N -delete` (at startup)."""
    subprocess.run(
        ["find", scratch_dir, "-type", "f", "-mmin", f"+{minutes}", "-delete"],
        check=False,
    )


def _build_model(settings: Settings) -> PyannoteDiarizer:
    model = PyannoteDiarizer(
        model_name=settings.diarization_model,
        revision=settings.diarization_revision,
        device=settings.device,
        hf_token=settings.hf_token,
        hf_home=settings.hf_home,
        use_fp16=settings.device == "cuda",
    )
    if settings.device == "cuda":
        model.load()
    elif settings.allow_cpu_models:
        logger.warning("cpu_model_fallback_allow_cpu_models=true")
        model.load()
    else:
        # DEVICE is not cuda and CPU is not allowed — crash at startup, not a half-started service.
        raise ModelLoadError("device_not_cuda_and_cpu_not_allowed")
    return model


def _consume_loop(
    settings: Settings,
    handler: DiarizationHandler,
    embedding_handler: EmbeddingHandler | None = None,
) -> None:
    """Two queues, one thread: diarization and voice embedding share one GPU.

    Polling order — `audio.embedding` first: the vector is needed interactively (lease class
    `interactive`), diarization is `offline` (ADR-006).
    """
    queue = RabbitMQQueue(settings.rabbitmq_url, prefetch=settings.rabbitmq_prefetch)
    for q in (QUEUE_DIARIZATION, QUEUE_EMBEDDING, QUEUE_TRANSCRIPTION, QUEUE_EVENTS):
        try:
            queue.declare(q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("queue_declare_failed queue=%s error=%s", q, type(exc).__name__)

    def _settle(q: str, delivery_tag, action: str, message: dict) -> None:
        if action == ACK:
            queue.ack(delivery_tag)
        elif action == NACK_RETRY:
            # requeue=False → the broker moves it to .retry (TTL 30s), attempt does not grow.
            queue.nack(delivery_tag, requeue=False)
        elif action == RETRY_WITH_ATTEMPT:
            # Retryable error with a bumped attempt: republish the updated body
            # to the main queue, ack the original (idempotent by job_id).
            queue.publish(q, message)
            queue.ack(delivery_tag)
        else:  # DEAD — substantive error: to .dead, ack the original
            queue.publish_dead(q, message)
            queue.ack(delivery_tag)

    workers = [(QUEUE_EMBEDDING, embedding_handler)]
    workers = [(q, h) for q, h in workers if h is not None]
    workers.append((QUEUE_DIARIZATION, handler))

    while True:
        try:
            consumers = [(q, h, queue.consume(q)) for q, h in workers]
            while True:
                idle = True
                for q, h, consumer in consumers:
                    message = next(consumer, None)
                    if not message:
                        continue
                    idle = False
                    delivery_tag = message.pop("_delivery_tag", None)
                    _settle(q, delivery_tag, h.handle(message), message)
                if idle:
                    time.sleep(0.2)
        except Exception as exc:  # noqa: BLE001
            # `str(exc)`, not just the class: a TypeError with no text turned a broken
            # consumer into 20 minutes of guessing on the stand (2026-11-01). The message
            # never carries a token or phrase text — only the call signature that broke.
            logger.warning(
                "consume_restart error=%s detail=%s", type(exc).__name__, str(exc)[:300]
            )
            time.sleep(2.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    install_logging(service="diarizer")

    _startup_scratch_cleanup(settings.scratch_dir, settings.scratch_cleanup_minutes)

    model = _build_model(settings)
    _state.model = model
    _state.loaded = bool(model.loaded)

    store = S3ObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        use_path_style=settings.s3_use_path_style,
    )
    repo = MongoSpeakerRepo(settings.mongo_url, settings.mongo_db)
    lease = RedisGpuLease(
        settings.gpu_lease_url,
        ttl_ms=settings.gpu_lease_ttl_ms,
        heartbeat_ms=settings.gpu_lease_heartbeat_ms,
    )
    handler = DiarizationHandler(
        settings=settings,
        model=model,
        store=store,
        repo=repo,
        queue=RabbitMQQueue(settings.rabbitmq_url, prefetch=1),
        normalizer=NormalizerAdapter(),
        lease=lease,
    )
    embedder = PyannoteEmbedder(
        pipeline_model=settings.diarization_model,
        revision=settings.diarization_revision,
        device=settings.device,
        hf_token=settings.hf_token,
        hf_home=settings.hf_home,
        use_fp16=settings.device == "cuda",
    )
    if _state.loaded or settings.allow_cpu_models:
        # Weights of the same family are already loaded by the diarization model; a separate
        # load — with no silent fallback to a foreign model (ADR-013).
        embedder.load()
        _state.embedding_loaded = embedder.loaded
    embedding_handler = EmbeddingHandler(
        settings=settings,
        model=embedder,
        store=store,
        repo=repo,
        queue=RabbitMQQueue(settings.rabbitmq_url, prefetch=1),
        normalizer=NormalizerAdapter(),
        lease=lease,
    )
    thread = threading.Thread(
        target=_consume_loop,
        args=(settings, handler, embedding_handler),
        daemon=True,
        name="diarizer-consume",
    )
    thread.start()

    try:
        yield
    finally:
        repo.close()


app = FastAPI(title="diarizer", lifespan=lifespan)


@app.get("/health")
async def health():
    if not _state.loaded:
        return JSONResponse(
            content={"status": "starting", "model": "loading", "gpu": "pending"},
            status_code=503,
        )
    return JSONResponse(
        content={
            "status": "ok",
            "model": "loaded",
            "embedding_model": "loaded" if _state.embedding_loaded else "pending",
            "gpu": "ok" if _state.gpu_ok else "down",
        },
        status_code=200,
    )
