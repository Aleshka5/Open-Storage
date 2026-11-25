"""asr-worker — GPU transcription worker (US-03): batches of turns → phrases.

`/health` answers `503` until the model is loaded (ADR-013: no silent fallback).
The endpoint returns the contract shape of `backend/asr-worker/api.md`:
`{status, model, gpu, active_stream}`. The model loads at startup (fp16 on CUDA); the queue
consumer runs in a separate thread. There is no public HTTP besides `/health`.
A model load failure means a crash at startup (not "half" started).

The stream (US-05) shares this process and the GPU; the hook for interrupting a batch between
turns (`_interrupted`) lives here, the WS endpoint itself is wired below.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse

from app.application.ports.asr_model import ModelLoadError
from app.application.ports.json_queue import QUEUE_TRANSCRIPTION
from app.application.transcribe_batch import (
    ACK,
    NACK_RETRY,
    RETRY_WITH_ATTEMPT,
    TranscribeBatchHandler,
)
from app.config import Settings, get_settings
from app.infrastructure.gpu_lease import RedisGpuLease
from app.infrastructure.minio_store import S3ObjectStore
from app.infrastructure.mongo import MongoPhraseRepo
from app.infrastructure.parakeet_model import ParakeetModel
from app.infrastructure.rabbitmq import QUEUE_EVENTS, RabbitMQQueue
from app.logging import install as install_logging

logger = logging.getLogger(__name__)


class WorkerState:
    def __init__(self) -> None:
        self.model: object = None
        self.loaded: bool = False
        self.gpu_ok: bool = True
        self.active_stream: bool = False
        self.stream_handler = None


_state = WorkerState()


def _build_model(settings: Settings) -> ParakeetModel:
    model = ParakeetModel(
        model_name=settings.asr_model,
        revision=settings.asr_revision,
        device=settings.device,
        hf_home=settings.hf_home,
        use_fp16=settings.device == "cuda",
        batch_size=settings.asr_gpu_batch_size,
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


def _consume_loop(settings: Settings, handler: TranscribeBatchHandler) -> None:
    queue = RabbitMQQueue(settings.rabbitmq_url, prefetch=settings.rabbitmq_prefetch)
    for q in (QUEUE_TRANSCRIPTION, QUEUE_EVENTS):
        try:
            queue.declare(q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("queue_declare_failed queue=%s error=%s", q, type(exc).__name__)

    while True:
        try:
            consumer = queue.consume(QUEUE_TRANSCRIPTION)
            for message in consumer:
                if message is None:
                    time.sleep(0.2)
                    continue
                delivery_tag = message.pop("_delivery_tag", None)
                action = handler.handle(message)
                if action == ACK:
                    queue.ack(delivery_tag)
                elif action == NACK_RETRY:
                    # requeue=False → the broker moves it to .retry (TTL 30s), attempt stays.
                    queue.nack(delivery_tag, requeue=False)
                elif action == RETRY_WITH_ATTEMPT:
                    # Retryable error with a bumped attempt: republish the updated body
                    # to the main queue, ack the original (idempotent by job_id).
                    queue.publish(QUEUE_TRANSCRIPTION, message)
                    queue.ack(delivery_tag)
                else:  # DEAD — substantive error: to .dead, ack the original
                    queue.publish_dead(QUEUE_TRANSCRIPTION, message)
                    queue.ack(delivery_tag)
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
    install_logging(service="asr-worker")

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
    repo = MongoPhraseRepo(settings.mongo_url, settings.mongo_db)
    lease = RedisGpuLease(
        settings.gpu_lease_url,
        ttl_ms=settings.gpu_lease_ttl_ms,
        heartbeat_ms=settings.gpu_lease_heartbeat_ms,
    )
    handler = TranscribeBatchHandler(
        settings=settings,
        model=model,
        store=store,
        repo=repo,
        queue=RabbitMQQueue(settings.rabbitmq_url, prefetch=settings.rabbitmq_prefetch),
        lease=lease,
    )
    thread = threading.Thread(
        target=_consume_loop, args=(settings, handler), daemon=True, name="asr-consume"
    )
    thread.start()

    # Stream (US-05): a separate session, the same model/repo, BUT its own GPU lease.
    # Sharing the lease object with the background transcribe loop is a race: `_token` is
    # mutable, and one owner's `release()` could free someone else's lease (D5). The Redis
    # key stays the same (`gpu:lease`), so mutual exclusion holds via SET NX.
    from app.application.stream_handler import StreamHandler  # noqa: PLC0415

    stream_lease = RedisGpuLease(
        settings.gpu_lease_url,
        ttl_ms=settings.gpu_lease_ttl_ms,
        heartbeat_ms=settings.gpu_lease_heartbeat_ms,
    )
    _state.stream_handler = StreamHandler(
        settings=settings, model=model, repo=repo, lease=stream_lease
    )

    try:
        yield
    finally:
        repo.close()


app = FastAPI(title="asr-worker", lifespan=lifespan)


@app.get("/health")
async def health():
    if not _state.loaded:
        return JSONResponse(
            content={
                "status": "starting",
                "model": "loading",
                "gpu": "pending",
                "active_stream": False,
            },
            status_code=503,
        )
    return JSONResponse(
        content={
            "status": "ok",
            "model": "loaded",
            "gpu": "ok" if _state.gpu_ok else "down",
            "active_stream": _state.active_stream,
        },
        status_code=200,
    )


@app.websocket("/v1/stream")
async def stream(websocket: WebSocket) -> None:
    """Live note recognition socket (asr-worker/api.md). The client is audio-api."""
    import json as _json

    from app.application.stream_handler import InvalidOpen  # noqa: PLC0415

    if not _state.loaded or _state.stream_handler is None:
        await websocket.close(code=4503)
        return

    # Complete the handshake BEFORE waiting for the `open` frame. Without `accept()` the
    # server never sends 101, the client waits for it, the server waits for its first frame —
    # a deadlock: the note socket closed as "ASR_UNAVAILABLE" after the client's timeout
    # (verified on the stand 2026-11-01).
    await websocket.accept()

    handler = _state.stream_handler
    # The first frame is a text `open`, no larger than 2 KB.
    try:
        first = await websocket.receive()
    except Exception as exc:  # noqa: BLE001
        logger.warning("stream_first_frame_error error=%s", type(exc).__name__)
        await websocket.close(code=4400)
        return

    if first.get("type") != "websocket.receive" or "text" not in first:
        await websocket.close(code=4400)
        return
    if first.get("bytes") is not None:
        await websocket.close(code=4400)
        return
    try:
        msg = _json.loads(first["text"])
    except (ValueError, TypeError):
        await websocket.close(code=4400)
        return

    # Open-frame validation (ownership, phrase, not_me_phrase) → 4404/4400.
    try:
        recording_id, phrase_id, owner_id = handler.validate_open(msg)
    except InvalidOpen as exc:
        logger.warning("stream_open_invalid code=%d", exc.close_code)
        await websocket.close(code=exc.close_code)
        return

    # Session slot + GPU lease (one session per process) → 4503.
    try:
        handler.acquire_slot()
    except InvalidOpen as exc:
        logger.warning("stream_gpu_busy code=%d", exc.close_code)
        await websocket.close(code=exc.close_code)
        return

    await websocket.send_text(
        _json.dumps(
            {
                "type": "ready",
                "recording_id": recording_id,
                "phrase_id": phrase_id,
                "sample_rate": 16000,
            }
        )
    )
    _state.active_stream = True

    async def _receive_stream():
        while True:
            try:
                frame = await websocket.receive()
            except Exception:  # noqa: BLE001
                break
            if frame.get("type") == "websocket.disconnect":
                break
            if frame.get("text") is not None:
                yield frame["text"]
            elif frame.get("bytes") is not None:
                yield frame["bytes"]

    try:
        await handler.loop(
            recording_id,
            phrase_id,
            owner_id,
            receive_stream=_receive_stream(),
            send_json=lambda d: websocket.send_text(_json.dumps(d)),
        )
        # The close reason comes from the handler: 1000 (normal), 4408 (no data for 30 s),
        # 4400 (frame overflow). The client tells them apart (asr-worker/api.md §Close).
        close_code = getattr(handler, "close_code", None) or 1000
        if close_code != 1000:
            logger.info("stream_close code=%d", close_code)
        await websocket.close(code=close_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stream_error error=%s", type(exc).__name__)
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
    finally:
        _state.active_stream = False
        handler.release_slot()
