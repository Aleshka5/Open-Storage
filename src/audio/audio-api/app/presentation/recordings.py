"""The `/api/recordings` router: UC-1..UC-5."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response

from app.application.poll_budget import PollBudget
from app.application.recording_service import PhraseService, RecordingService
from app.presentation.container import Container
from app.presentation.dependencies import get_current_owner
from app.presentation.schemas import TitleUpdate

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _recordings_service() -> RecordingService:
    return Container.instance().recording_service


def _phrase_service() -> PhraseService:
    return Container.instance().phrase_service


def _poll_budget() -> PollBudget:
    return Container.instance().poll_budget


@router.post("", status_code=201)
async def upload_recording(
    file: Annotated[UploadFile, File()],
    record_service: Annotated[RecordingService, Depends(_recordings_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
    title: Annotated[str | None, Form()] = None,
):
    """File intake: ffprobe → MinIO → recordings{uploaded} → audio.diarization."""

    async def _chunks() -> AsyncIterator[bytes]:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    return await record_service.upload(
        owner_id,
        filename=file.filename or "recording",
        read_chunks=_chunks(),
        title=title,
    )


@router.get("")
async def list_recordings(
    record_service: Annotated[RecordingService, Depends(_recordings_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
):
    return await record_service.list(owner_id, limit=limit, cursor=cursor)


@router.get("/{recording_id}")
async def get_recording(
    recording_id: str,
    record_service: Annotated[RecordingService, Depends(_recordings_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    return await record_service.get(owner_id, recording_id)


@router.patch("/{recording_id}")
async def rename_recording(
    recording_id: str,
    body: TitleUpdate,
    record_service: Annotated[RecordingService, Depends(_recordings_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    return await record_service.rename(owner_id, recording_id, body.title)


@router.get("/{recording_id}/phrases")
async def list_phrases(
    recording_id: str,
    phrase_service: Annotated[PhraseService, Depends(_phrase_service)],
    budget: Annotated[PollBudget, Depends(_poll_budget)],
    owner_id: Annotated[str, Depends(get_current_owner)],
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    # US-08: the polling budget (disabled by default: the limit is held by the gateway).
    budget.check(owner_id)
    return await phrase_service.list_phrases(
        owner_id, recording_id, after_seq=after_seq, limit=limit
    )


def _parse_range(header: str | None, size: int) -> tuple[int, int | None]:
    """Parses `Range: bytes=a-b`; returns (start, length). No range → (-1, None)."""
    if not header or not header.startswith("bytes="):
        return -1, None
    spec = header[6:].strip()
    if spec.startswith("-"):
        # suffix: bytes=-N → the last N bytes.
        n = int(spec[1:])
        return max(0, size - n), min(n, size)
    a, _, b = spec.partition("-")
    start = int(a) if a else 0
    end = int(b) if b else size - 1
    length = max(0, end - start + 1)
    return start, length


@router.head("/{recording_id}/audio")
@router.get("/{recording_id}/audio")
async def get_audio(
    recording_id: str,
    request: Request,
    record_service: Annotated[RecordingService, Depends(_recordings_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """Audio proxy from MinIO with Range support (ADR-010, bucket-and-keys.md).

    `recording`/`finalizing` → 409 AUDIO_NOT_READY; past the end → 416;
    otherwise 200 (whole) / 206 (Range).
    """
    meta = await record_service.audio_meta(owner_id, recording_id)
    size = meta["size"]
    range_header = request.headers.get("range")
    start, length = _parse_range(range_header, size)

    if start < 0:
        # No Range — the whole object.
        data, total, ctype, _key, _s = await record_service.audio_range(
            owner_id, recording_id, start=0, length=None
        )
        return Response(
            content=data,
            media_type=ctype,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(total),
                "Cache-Control": "private, max-age=3600",
            },
        )

    if start >= size:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{size}"},
        )

    data, _total, ctype, _key, _s = await record_service.audio_range(
        owner_id, recording_id, start=start, length=length
    )
    end = start + len(data) - 1 if data else start - 1
    return Response(
        content=data,
        status_code=206,
        media_type=ctype,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(len(data)),
            "Cache-Control": "private, max-age=3600",
        },
    )
