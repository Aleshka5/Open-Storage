"""FastAPI application factory with lifespan (indexes, event consumer, watchdog)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.domain.app_error import AppError
from app.logging import install as install_logging
from app.presentation.container import Container
from app.presentation.errors import register_exception_handlers
from app.presentation.health import router as health_router
from app.presentation.me import router as me_router
from app.presentation.nick import router as nick_router
from app.presentation.recordings import router as recordings_router
from app.presentation.voice_notes import router as voice_notes_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # US-08: one JSON format per process, before the first INFO. Idempotent.
    install_logging(service="audio-api")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = Container.build(settings)
        from app.infrastructure.mongo import create_indexes

        try:
            created = await create_indexes(container.mongo_db)
            logger.info("indexes_ready count=%d", len(created))
        except Exception as exc:  # noqa: BLE001
            logger.warning("index_creation_failed error=%s", type(exc).__name__)

        # The `audio_voices` collection is created at startup if it does not exist (collection.md).
        # A dimension mismatch — VOICE_INDEX_INCOMPATIBLE (logged, does not break),
        # Qdrant unavailable — VOICE_INDEX_UNAVAILABLE (suggestions fail, nicks live).
        try:
            await container.voice_index.ensure_collection(settings.voice_embedding_size)
        except AppError as exc:
            logger.warning("voice_index_init_failed error=%s", exc.code.value)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "voice_index_init_failed error=%s", type(exc).__name__
            )

        tasks = [
            asyncio.create_task(_events_loop(container)),
            asyncio.create_task(_watchdog_loop(container)),
        ]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if container.queue is not None:
                container.queue.close()
            if container.mongo_client is not None:
                container.mongo_client.close()

    app = FastAPI(title="audio-api", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(recordings_router)
    app.include_router(nick_router)
    app.include_router(me_router)
    app.include_router(voice_notes_router)
    return app


async def _events_loop(container: Container) -> None:
    """Reads audio.events and applies status transitions."""
    from app.infrastructure.rabbitmq import QUEUE_EVENTS

    queue = container.queue
    applier = container.events_applier
    try:
        queue.declare(QUEUE_EVENTS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("queue_declare_failed error=%s", type(exc).__name__)
        return

    consumer = queue.consume(QUEUE_EVENTS)
    while True:
        try:
            try:
                message = next(consumer)
            except StopIteration:
                break
            await asyncio.sleep(0.1)
            if message is None:
                continue
            delivery_tag = message.pop("_delivery_tag", None)
            # ADR-009: an unknown schema_version → .dead (unsupported_schema), we do not parse it.
            if message.get("schema_version") != 1:
                logger.warning("unsupported_schema version=%s", message.get("schema_version"))
                queue.nack(delivery_tag, requeue=False)
                continue
            event = message.get("event")
            recording_id = message.get("recording_id")
            owner_id = message.get("owner_user_id")
            if not event or not recording_id or not owner_id:
                queue.ack(delivery_tag)
                continue
            await applier.apply(
                event, recording_id, owner_id, message.get("data") or {}
            )
            queue.ack(delivery_tag)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("events_loop_error error=%s", type(exc).__name__)
            await asyncio.sleep(1.0)


async def _watchdog_loop(container: Container) -> None:
    """Every 30 s — the stall watchdog for stuck recordings."""
    watchdog = container.stall_watchdog
    while True:
        try:
            await asyncio.sleep(30.0)
            n = await watchdog.sweep()
            if n:
                logger.info("stall_sweep marked=%d", n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("watchdog_error error=%s", type(exc).__name__)
