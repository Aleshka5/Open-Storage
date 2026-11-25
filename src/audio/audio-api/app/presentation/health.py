"""The `/health` router — public (gateway `auth: public`, requires no identity).

Aggregated response (US-08, item 2): `{status, mongo, minio, qdrant, rabbitmq, asr}`.

Status rule:

- `mongo` and `minio` are **required**: any `down` → `503`, `status: "down"` and
  `error_code: STORAGE_UNAVAILABLE` in the body. Without them nothing is written at all.
- `qdrant` is needed by nick suggestions and the "Me" voice, but the chat and player live without it
  (ADR-008). `down` → `200` with `status: "degraded"`: the index is repaired separately and must not
  break `make up`.
- `rabbitmq` and `asr` — `down` yields `200` with `status: "degraded"`: an upload answers
  `503 QUEUE_UNAVAILABLE` / `ASR_UNAVAILABLE`, while an open chat keeps reading
  (acceptance criterion "a killed asr-worker does not break reading").

The checks run in parallel, external HTTP checks have a 2 s timeout: `/health` answers
quickly even when every dependency is down.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.domain.errors import ErrorCode
from app.presentation.container import Container

logger = logging.getLogger(__name__)

router = APIRouter()

# Required storages: their failure is a 503. The rest degrade but do not break.
REQUIRED = ("mongo", "minio")


def _container() -> Container:
    return Container.instance()


@router.get("/health")
async def health(container: Annotated[Container, Depends(_container)]):
    settings = container.settings

    mongo_ok, minio_ok, qdrant_ok, rabbitmq_ok, asr_ok = await asyncio.gather(
        _mongo_ok(container.repo),
        _minio_ok(container.store),
        _qdrant_ok(settings.qdrant_url),
        asyncio.to_thread(_rabbitmq_ok, container.queue),
        _asr_ok(settings.asr_stream_url),
    )
    checks = {
        "mongo": mongo_ok,
        "minio": minio_ok,
        "qdrant": qdrant_ok,
        "rabbitmq": rabbitmq_ok,
        "asr": asr_ok,
    }
    down = [name for name, ok in checks.items() if not ok]
    required_down = [name for name in REQUIRED if name in down]

    if required_down:
        status = "down"
    elif down:
        status = "degraded"
    else:
        status = "ok"

    body: dict[str, object] = {"status": status}
    body.update({name: ("ok" if ok else "down") for name, ok in checks.items()})
    if required_down:
        body["error_code"] = ErrorCode.STORAGE_UNAVAILABLE.value
        body["down"] = required_down

    logger.info(
        "health_probe status=%s stage=health error_code=%s down=%s",
        status,
        ErrorCode.STORAGE_UNAVAILABLE.value if required_down else "NONE",
        ",".join(down) or "NONE",
    )
    return JSONResponse(status_code=503 if required_down else 200, content=body)


async def _mongo_ok(repo) -> bool:
    """`ping` via motor; fakes without a database count as alive."""
    try:
        database = getattr(getattr(repo, "_recordings", None), "database", None)
        if database is None:
            return True
        ping = await database.command("ping")
        return ping.get("ok") == 1.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("mongo_check_failed error=%s", type(exc).__name__)
        return False


async def _minio_ok(store) -> bool:
    """`list_objects_v2` over the bucket — the same way `MinioAudioStore.check()` does it."""
    try:
        return bool(await store.check())
    except Exception as exc:  # noqa: BLE001 — any failure = down
        logger.warning("minio_check_failed error=%s", type(exc).__name__)
        return False


def _rabbitmq_ok(queue) -> bool:
    """pika is synchronous: the caller moves it to a thread via `asyncio.to_thread`."""
    try:
        return bool(queue.is_available())
    except Exception as exc:  # noqa: BLE001
        logger.warning("rabbitmq_check_failed error=%s", type(exc).__name__)
        return False


async def _qdrant_ok(url: str | None) -> bool:
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/collections")
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def _asr_ok(ws_url: str | None) -> bool:
    """`asr-worker` is alive: its `/health` returns 200 only with the model loaded (ADR-013)."""
    if not ws_url:
        return False
    # WS URL `ws://asr-worker:8020/v1/stream` -> HTTP `http://asr-worker:8020/health`
    http_url = ws_url.replace("ws://", "http://").replace("/v1/stream", "/health")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(http_url)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        # The normal startup state: asr down does not break /health and writes no noise to the log.
        return False
