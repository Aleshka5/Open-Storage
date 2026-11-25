"""Infrastructure: ASR stream client via `websockets` (asr-worker /v1/stream).

`audio-api` connects to `asr-worker:8020` and relays the browser's PCM. Frame format —
`docs/backend/asr-worker/api.md`. Slot occupancy (`4503`), service unavailability and
ASR errors are translated into `AsrStreamError`, so presentation can return a clear code.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import websockets

from app.application.ports.asr_stream import AsrStreamError

logger = logging.getLogger(__name__)


class WebsocketAsrStream:
    """One live channel to asr-worker. Fully async (matches the audio-api loop)."""

    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._ws = None
        self._close_code: int | None = None

    async def open(self, *, recording_id: str, phrase_id: str, owner_id: str) -> None:
        try:
            self._ws = await websockets.connect(self._ws_url)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 — network/refused
            raise AsrStreamError("ASR_UNAVAILABLE", "Recognition unavailable") from exc
        await self._ws.send(
            json.dumps(
                {
                    "type": "open",
                    "recording_id": recording_id,
                    "phrase_id": phrase_id,
                    "owner_user_id": owner_id,
                    "format": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1,
                }
            )
        )

    async def send_pcm(self, data: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(data)

    async def send_stop(self) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps({"type": "stop"}))

    async def recv(self) -> dict[str, Any] | None:
        if self._ws is None:
            return None
        try:
            raw = await self._ws.recv()
        except websockets.ConnectionClosed as exc:  # type: ignore[attr-defined]
            self._close_code = exc.code
            return None
        if isinstance(raw, bytes):
            return {"type": "pcm", "data": raw}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def close_code(self) -> int | None:
        return self._close_code

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None


class WebsocketAsrStreamFactory:
    """Creates `WebsocketAsrStream` for a given `ws_url` (from the settings)."""

    def connect(self, ws_url: str) -> WebsocketAsrStream:
        return WebsocketAsrStream(ws_url)
