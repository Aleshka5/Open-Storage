"""The voice notes router `/api/voice-notes` (US-05, UC-7).

POST creates a `recording` + SELF speaker + phrase seq=1 and returns `ws_url`.
WS `/api/voice-notes/{id}/stream` takes 100 ms PCM frames (3200 bytes) and sends
`ready/partial/final/stopped/done/error`. Identity is the `X-Auth-Subject` header,
supplied by the gateway also on Upgrade.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.application.voice_note_service import VoiceNoteService
from app.presentation.container import Container
from app.presentation.dependencies import get_current_owner, owner_from_header_value

router = APIRouter(prefix="/api/voice-notes", tags=["voice-notes"])


def _service() -> VoiceNoteService:
    return Container.instance().voice_note_service


@router.post("", status_code=201)
async def create_voice_note(
    service: Annotated[VoiceNoteService, Depends(_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """Creates the note and its first phrase BEFORE the socket opens (api.md)."""
    return await service.create(owner_id)


@router.websocket("/{recording_id}/stream")
async def voice_note_stream(
    websocket: WebSocket,
    recording_id: str,
    service: Annotated[VoiceNoteService, Depends(_service)],
):
    """PCM stream → asr-worker /v1/stream, multipart to MinIO, text back to the browser."""
    # The gateway sets identity on Upgrade through the header (as in HTTP).
    owner_id = owner_from_header_value(websocket.headers.get("X-Auth-Subject"))

    await websocket.accept()

    async def _receive():
        while True:
            frame = await websocket.receive()
            if frame.get("type") == "websocket.disconnect":
                return None
            if frame.get("text") is not None:
                try:
                    return json.loads(frame["text"])
                except (ValueError, TypeError):
                    return {"type": "unknown"}
            if frame.get("bytes") is not None:
                return frame["bytes"]
            return None

    async def _send_text(msg: dict) -> None:
        await websocket.send_text(json.dumps(msg))

    async def _close(code: int) -> None:
        await websocket.close(code=code)

    try:
        await service.run_stream(
            owner_id,
            recording_id,
            receive=_receive,
            send_text=_send_text,
            close=_close,
        )
    except WebSocketDisconnect:
        # The browser dropped the socket: `receive` returned None, run_stream has already finalized.
        pass
