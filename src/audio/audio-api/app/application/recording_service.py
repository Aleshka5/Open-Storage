"""Recording scenarios: UC-1 client upload, UC-2 list, UC-3 details, UC-4 rename.

Write order (ADR-011): object in MinIO -> recordings document -> job publish.
If publishing fails, the recording is visible as `failed (queue_unavailable)`, the object is not
deleted.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.application.ports.audio_store import AudioStore
from app.application.ports.json_queue import JsonQueue
from app.application.ports.recording_repo import RecordingRepo
from app.application.ports.voice_repo import VoiceRepo
from app.config import Settings
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.media import ProbeResult, add_stream_index, extension_for, probe
from app.domain.recording import Recording, audio_key_for
from app.domain.status import RecordingStatus

DIARIZATION_QUEUE = "audio.diarization"
SCHEMA_VERSION = 1

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _elapsed_ms(started: float) -> int:
    """Milliseconds since `started` (`time.monotonic()`)."""
    return int((time.monotonic() - started) * 1000)


class RecordingService:
    def __init__(
        self,
        repo: RecordingRepo,
        store: AudioStore,
        queue: JsonQueue,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._store = store
        self._queue = queue
        self._settings = settings

    async def upload(
        self,
        owner_id: str,
        filename: str,
        read_chunks,
        title: str | None = None,
    ) -> dict[str, Any]:
        """UC-1: multipart intake, ffprobe, MinIO write, document, publish.

        `read_chunks` is the async-iterable source of the file bytes. The limit is checked as
        reading proceeds (413 before the full write). Returns the recording object for the response.
        """
        recording_id = str(uuid.uuid4())
        started = time.monotonic()
        # US-08: the file name and the title are user data and do not go to the log.
        # The run trace is only recording_id/job_id/stage/duration_ms/error_code.

        # 1. Read into a scratch file in chunks, checking MAX_UPLOAD_BYTES on the fly.
        scratch = self._spool(recording_id)
        total = 0
        limit = self._settings.max_upload_bytes
        try:
            with scratch.open("wb") as fh:
                async for chunk in read_chunks:
                    total += len(chunk)
                    if total > limit:
                        raise AppError(
                            ErrorCode.PAYLOAD_TOO_LARGE,
                            "File exceeds the allowed limit",
                        )
                    fh.write(chunk)
        except AppError:
            scratch.unlink(missing_ok=True)
            raise

        if total == 0:
            scratch.unlink(missing_ok=True)
            raise AppError(ErrorCode.UNSUPPORTED_MEDIA, "Empty file")

        # 2. ffprobe: audio validation. 415 if not audio / container not in the list.
        try:
            probed: ProbeResult = probe(scratch)
        except ValueError as exc:
            scratch.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.UNSUPPORTED_MEDIA,
                f"File is not supported audio: {exc}",
            ) from exc

        ext = extension_for(filename) or probed.container or "bin"
        audio_key = audio_key_for(owner_id, recording_id, ext)
        title = (title or Path(filename).stem or "Recording")[:120]
        now = _iso_now()

        # 3. Object in MinIO. An MPEG stream without an index is rewritten with one
        # (`-c copy`: audio frames untouched) — otherwise the player's timeline and any
        # seek use a bitrate estimate as the duration (ADR-010).
        stored_path = scratch
        indexed_path: Path | None = None
        if probed.needs_index:
            indexed_path = scratch.with_name(f"{scratch.name}.indexed.{ext or 'mp3'}")
            if add_stream_index(scratch, indexed_path):
                stored_path = indexed_path
                logger.info(
                    "upload_indexed recording_id=%s declared_duration_ms=%s duration_ms=%s",
                    recording_id,
                    probed.declared_duration_ms,
                    probed.duration_ms,
                )
            else:
                logger.warning("upload_index_failed recording_id=%s", recording_id)
                indexed_path = None
        stored_bytes = stored_path.stat().st_size if stored_path is not scratch else total
        try:
            await self._store.put_object_stream(
                audio_key,
                probed.content_type,
                _file_reader(stored_path),
                size_hint=stored_bytes,
                owner_id=owner_id,
                recording_id=recording_id,
            )
        except Exception as exc:
            scratch.unlink(missing_ok=True)
            if indexed_path is not None:
                indexed_path.unlink(missing_ok=True)
            logger.warning(
                "upload_failed stage=upload error_code=STORAGE_UNAVAILABLE "
                "recording_id=%s duration_ms=%d",
                recording_id,
                _elapsed_ms(started),
            )
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE,
                "Storage unavailable",
            ) from exc
        scratch.unlink(missing_ok=True)
        if indexed_path is not None:
            indexed_path.unlink(missing_ok=True)

        recording = Recording(
            recording_id=recording_id,
            owner_user_id=owner_id,
            title=title,
            kind="upload",
            status=RecordingStatus.UPLOADED,
            audio_key=audio_key,
            audio_content_type=probed.content_type,
            audio_bytes=stored_bytes,
            duration_ms=probed.duration_ms,
            created_at=now,
            updated_at=now,
        )
        recording.processing = recording.default_processing()

        # 4. recordings document (uploaded).
        try:
            await self._repo.insert_recording(recording)
        except Exception as exc:
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE, "Storage unavailable"
            ) from exc

        # 5. Publishing the diarization job.
        job_id = str(uuid.uuid4())
        message = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "recording_id": recording_id,
            "owner_user_id": owner_id,
            "audio_key": audio_key,
            "content_type": probed.content_type,
            "attempt": 0,
            "created_at": now,
        }
        try:
            self._queue.publish(
                DIARIZATION_QUEUE,
                message,
                message_id=job_id,
                correlation_id=recording_id,
            )
        except Exception as exc:
            # The recording was created as failed (queue_unavailable); the object is not deleted.
            await self._repo.set_status(
                recording_id,
                owner_id,
                status=RecordingStatus.FAILED.value,
                error_code="queue_unavailable",
            )
            logger.warning(
                "upload_failed stage=upload error_code=QUEUE_UNAVAILABLE "
                "recording_id=%s job_id=%s duration_ms=%d",
                recording_id,
                job_id,
                _elapsed_ms(started),
            )
            raise AppError(
                ErrorCode.QUEUE_UNAVAILABLE,
                "Broker unavailable",
                recording_id=recording_id,
            ) from exc

        logger.info(
            "upload_done stage=upload recording_id=%s job_id=%s duration_ms=%d "
            "error_code=NONE",
            recording_id,
            job_id,
            _elapsed_ms(started),
        )
        return self._to_public(recording, owner_id)

    async def list(
        self, owner_id: str, *, limit: int, cursor: str | None
    ) -> dict[str, Any]:
        items, next_cursor = await self._repo.list_recordings(
            owner_id, limit=limit, cursor=cursor
        )
        return {
            "items": [self._to_list_item(d) for d in items],
            "next_cursor": next_cursor,
        }

    async def get(self, owner_id: str, recording_id: str) -> dict[str, Any]:
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        return {
            "recording": self._to_detail(doc),
            "speakers": [],  # US-02: empty, the field is already in the contract
        }

    async def rename(self, owner_id: str, recording_id: str, title: str) -> dict[str, Any]:
        ok = await self._repo.update_title(recording_id, owner_id, title)
        if not ok:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        doc = await self._repo.get_recording(recording_id, owner_id)
        return self._to_detail(doc)  # type: ignore[arg-type]

    async def audio_meta(self, owner_id: str, recording_id: str) -> dict[str, Any]:
        """Object metadata for HEAD/GET /audio; 409 for recording/finalizing."""
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        status = doc.get("status")
        if status in (RecordingStatus.RECORDING.value, RecordingStatus.FINALIZING.value):
            raise AppError(
                ErrorCode.AUDIO_NOT_READY,
                "Audio is still being written",
                recording_id=recording_id,
            )
        key = doc.get("audio_key")
        if not key:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        stat = await self._store.stat_object(key)
        if stat is None:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        return {
            "key": key,
            "content_type": stat.get("content_type", "application/octet-stream"),
            "size": int(stat.get("size") or 0),
            "etag": stat.get("etag"),
        }

    async def audio_range(
        self, owner_id: str, recording_id: str, *, start: int, length: int | None
    ) -> tuple[bytes, int, str, str, int]:
        """Reads an audio range; returns (data, total, content_type, key, etag_size).

        For the Range proxy (ADR-010): the browser pulls parts of the object, not the whole thing.
        """
        meta = await self.audio_meta(owner_id, recording_id)
        data, total = await self._store.get_object_range(
            meta["key"], start=start, length=length
        )
        return data, total, meta["content_type"], meta["key"], meta["size"]

    @staticmethod
    def _spool(recording_id: str) -> Path:
        import tempfile

        return Path(tempfile.gettempdir()) / f"audio-api-{recording_id}"

    @staticmethod
    def _to_public(recording: Recording, owner_id: str) -> dict[str, Any]:
        return {
            "id": recording.recording_id,
            "title": recording.title,
            "kind": recording.kind,
            "status": recording.status.value,
            "duration_ms": recording.duration_ms,
            "is_default_voice": recording.is_default_voice,
            "created_at": recording.created_at,
            "audio": {
                "content_type": recording.audio_content_type,
                "bytes": recording.audio_bytes,
            },
            "processing": recording.processing,
        }

    @staticmethod
    def _to_list_item(doc: dict[str, Any]) -> dict[str, Any]:
        processing = doc.get("processing") or {}
        progress = None
        if processing.get("phrases_total"):
            progress = {
                "phrases_done": processing.get("phrases_done", 0),
                "phrases_total": processing.get("phrases_total", 0),
            }
        return {
            "id": doc["_id"],
            "title": doc.get("title"),
            "kind": doc.get("kind"),
            "status": doc.get("status"),
            "duration_ms": doc.get("duration_ms"),
            "is_default_voice": doc.get("is_default_voice", False),
            "created_at": doc.get("created_at"),
            "progress": progress,
        }

    @staticmethod
    def _to_detail(doc: dict[str, Any]) -> dict[str, Any]:
        processing = doc.get("processing") or {}
        return {
            "id": doc["_id"],
            "title": doc.get("title"),
            "kind": doc.get("kind"),
            "status": doc.get("status"),
            "duration_ms": doc.get("duration_ms"),
            "language": doc.get("language"),
            "is_default_voice": doc.get("is_default_voice", False),
            "audio": {
                "content_type": doc.get("audio_content_type"),
                "bytes": doc.get("audio_bytes", 0),
            },
            "processing": {
                "error_code": processing.get("error_code"),
                "phrases_done": processing.get("phrases_done", 0),
                "phrases_total": processing.get("phrases_total", 0),
            },
            "created_at": doc.get("created_at"),
            "ready_at": doc.get("ready_at"),
        }


def _file_reader(path: Path):
    """Turns a file on disk into a synchronous reader for aioboto3 put_object (Body)."""
    return open(path, "rb")  # noqa: SIM115 — closed inside aioboto3 after the upload


class PhraseService:
    """UC-5: incremental polling of the growing chat.

    The recording status comes from `RecordingRepo`; phrases come from `VoiceRepo.list_phrases`
    (the label is joined at read time from `speakers`, ADR-004). US-04: the chat fills in by itself.
    """

    def __init__(
        self,
        repo: RecordingRepo,
        settings: Settings,
        voice_repo: VoiceRepo | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._voice_repo = voice_repo

    async def list_phrases(
        self,
        owner_id: str,
        recording_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> dict[str, Any]:
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None:
            raise AppError(
                ErrorCode.NOT_FOUND, "Recording not found", recording_id=recording_id
            )
        processing = doc.get("processing") or {}

        items: list[dict[str, Any]] = []
        next_after_seq = after_seq
        if self._voice_repo is not None:
            items, next_after_seq = await self._voice_repo.list_phrases(
                recording_id, owner_id, after_seq=after_seq, limit=limit
            )

        return {
            "recording": {
                "status": doc.get("status"),
                "processing": {
                    "phrases_done": processing.get("phrases_done", 0),
                    "phrases_total": processing.get("phrases_total", 0),
                },
            },
            "items": items,
            "next_after_seq": next_after_seq,
        }
