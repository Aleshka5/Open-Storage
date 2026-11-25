"""Voice note scenario (UC-7): creation and the WS recognition stream.

Control flow (docs/backend/audio-api/api.md §POST /api/voice-notes, §WS stream,
ADR-003/006/012):

1. `create()`: ASR availability check → "Note N" counter → `recording` document →
   `SELF` speaker (label Me, is_me true, centroid null) → empty phrase `seq=1`
   (`side=right`, `state=partial`) → response with `recording_id` and `ws_url`.

2. `run_stream()`: opens a socket to asr-worker, relays the browser's PCM frames,
   writes them to MinIO multipart (5 MiB parts) with backpressure, sends to the browser
   `ready/partial/final/stopped/done/error`. On `stop`/disconnect/timeout — finalization:
   last chunk → `CompleteMultipartUpload` → `stopped` → `done` → close `1000`.

3. Finalization publishes `audio.embedding` (queue-audio-embedding/message.md): the note's
   voice vector is computed by `diarizer` after the object is closed, so that "Make it my voice"
   is instant. A note shorter than `MIN_EMBED_SECONDS` (1 s) — the job is not published:
   no vector appears, `processing.embedding` goes straight to `failed`, `PUT /api/me/voice` answers
   `409 VOICE_NOT_READY`.

Field writers (data-model.md, ownership map): `audio-api` creates the recording and the
`SELF` speaker, writes `recordings.status`; `asr-worker` writes `phrases.text/state/revision/end_ms`
and saves the result to Mongo itself — `audio-api` only relays the text to the browser.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.application.ports.asr_stream import AsrStreamError, AsrStreamFactory
from app.application.ports.audio_store import AudioStore
from app.application.ports.json_queue import JsonQueue
from app.application.ports.recording_repo import RecordingRepo
from app.application.ports.voice_repo import VoiceRepo
from app.config import Settings
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.recording import Recording, note_key_for
from app.domain.status import RecordingStatus
from app.infrastructure.pcm_muxer import (
    MuxerError,
    MuxerUnavailable,
    PcmMuxer,
    default_muxer_factory,
)

logger = logging.getLogger(__name__)

# Multipart upload part size: 5 MiB (ADR-012, bucket-and-keys.md).
PART_SIZE = 5 * 1024 * 1024

# The note codec is fixed (ADR-012, item 6, bucket-and-keys.md): WebM/Opus.
AUDIO_CONTENT_TYPE = "audio/webm"

# WS close on idle: no data for 30 s (audio-api/api.md).
CLOSE_IDLE_TIMEOUT = 4408
CLOSE_NORMAL = 1000
CLOSE_NOT_FOUND = 4404
CLOSE_BAD_REQUEST = 4400
CLOSE_STORAGE = 4500

# PCM s16le 16 kHz: 2 bytes per sample → 32 bytes per millisecond.
BYTES_PER_MS = 32

# Note voice vector queue: published by audio-api, consumed by diarizer (broker.md).
QUEUE_EMBEDDING = "audio.embedding"
SCHEMA_VERSION = 1
# The only `target` in the contract; the field is extensible (later — `speaker`).
EMBED_TARGET_VOICE_NOTE = "voice_note"


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MultipartWriter:
    """Writes bytes to MinIO in 5 MiB parts without buffering in memory (ADR-012)."""

    def __init__(self, store: AudioStore, key: str) -> None:
        self._store = store
        self._key = key
        self.upload_id: str | None = None
        self.parts: list[dict[str, Any]] = []
        self._buf = bytearray()
        self._part_number = 0
        self.total_bytes = 0
        # Incoming PCM bytes — for duration_ms and the "was there audio / was there none" decision.
        self.pcm_bytes = 0

    async def open(self) -> None:
        self.upload_id = await self._store.create_multipart(self._key, AUDIO_CONTENT_TYPE)

    async def write(self, data: bytes) -> None:
        self.total_bytes += len(data)
        self._buf.extend(data)
        if len(self._buf) >= PART_SIZE:
            await self._flush_part()

    async def write_pcm(self, pcm: bytes) -> None:
        """PCM from the browser: feeds the duration requirement, not the object."""
        self.pcm_bytes += len(pcm)

    async def complete(self) -> None:
        if self._buf:
            await self._flush_part()
        if self.upload_id is not None:
            await self._store.complete_multipart(self._key, self.upload_id, self.parts)

    async def abort(self) -> None:
        if self.upload_id is not None:
            await self._store.abort_multipart(self._key, self.upload_id)
            self.upload_id = None

    async def _flush_part(self) -> None:
        self._part_number += 1
        etag = await self._store.upload_part(
            self._key, self.upload_id, self._part_number, bytes(self._buf)
        )
        self.parts.append({"PartNumber": self._part_number, "ETag": etag})
        self._buf = bytearray()


class VoiceNoteService:
    """Note creation and the live recognition stream through asr-worker."""

    def __init__(
        self,
        repo: RecordingRepo,
        voice_repo: VoiceRepo,
        store: AudioStore,
        asr_factory: AsrStreamFactory,
        settings: Settings,
        asr_probe: Callable[[], Awaitable[tuple[bool, bool]]] | None = None,
        queue: JsonQueue | None = None,
    ) -> None:
        self._repo = repo
        self._voice_repo = voice_repo
        self._store = store
        self._asr_factory = asr_factory
        self._settings = settings
        # The queue is needed only at finalization (`audio.embedding`). None — a deployment
        # without a broker: the note is recorded, the vector is simply not computed.
        self._queue = queue
        self._asr_probe = asr_probe
        # ffmpeg muxer PCM → WebM/Opus on the fly (ADR-012, item 6). One factory per session.
        self._muxer_factory: Callable[[], PcmMuxer] = default_muxer_factory(
            settings.ffmpeg_path
        )

    # -- creation -----------------------------------------------------------

    async def create(self, owner_id: str) -> dict[str, Any]:
        """UC-7 step 1: `recording` document + SELF speaker + phrase seq=1. No socket."""
        available, busy = await self._probe_asr()
        if not available:
            raise AppError(ErrorCode.ASR_UNAVAILABLE, "Recognition unavailable")
        if busy:
            raise AppError(ErrorCode.ASR_BUSY, "Recognition is busy")

        recording_id = str(uuid.uuid4())
        speaker_id = str(uuid.uuid4())
        phrase_id = str(uuid.uuid4())
        now = _iso_now()

        n = await self._repo.next_note_counter(owner_id)
        title = f"Note {n}"

        recording = Recording(
            recording_id=recording_id,
            owner_user_id=owner_id,
            title=title,
            kind="voice_note",
            status=RecordingStatus.RECORDING,
            audio_key=note_key_for(owner_id, recording_id),
            audio_content_type="audio/webm",
            audio_bytes=0,
            duration_ms=0,
            created_at=now,
            updated_at=now,
        )
        recording.processing = recording.default_processing()

        try:
            await self._repo.insert_recording(recording)
            await self._voice_repo.create_self_speaker(recording_id, owner_id, speaker_id)
            await self._voice_repo.create_note_phrase(
                recording_id, owner_id, phrase_id=phrase_id, speaker_id=speaker_id
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE, "Storage unavailable"
            ) from exc

        return {
            "recording_id": recording_id,
            "title": title,
            "phrase_id": phrase_id,
            "speaker_id": speaker_id,
            "ws_url": f"/api/voice-notes/{recording_id}/stream",
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
        }

    async def _probe_asr(self) -> tuple[bool, bool]:
        """(available, busy) via asr-worker /health: an active session means ASR_BUSY."""
        if self._asr_probe is not None:
            return await self._asr_probe()
        import httpx

        url = self._settings.asr_stream_url or ""
        http_url = url.replace("ws://", "http://").replace("wss://", "https://")
        http_url = http_url.replace("/v1/stream", "/health")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(http_url)
            if r.status_code != 200:
                return False, False
            body = r.json()
            return True, bool(body.get("active_stream", False))
        except Exception:  # noqa: BLE001
            return False, False

    async def load_for_stream(self, owner_id: str, recording_id: str) -> dict[str, Any] | None:
        """The recording used for validation on socket open (or None if foreign/not a note)."""
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None or doc.get("kind") != "voice_note":
            return None
        return doc

    async def phrase_id_for(self, owner_id: str, recording_id: str) -> str:
        items, _ = await self._voice_repo.list_phrases(
            recording_id, owner_id, after_seq=0, limit=1
        )
        if items:
            return items[0]["id"]
        return ""

    # -- stream -------------------------------------------------------------

    async def run_stream(
        self,
        owner_id: str,
        recording_id: str,
        *,
        receive: Callable[[], Awaitable[dict[str, Any] | bytes | None]],
        send_text: Callable[[dict[str, Any]], Awaitable[None]],
        close: Callable[[int], Awaitable[None]],
    ) -> None:
        """Drives one note from the opened WS to finalization.

        `receive()` returns a text frame (dict with `type`), a PCM frame (bytes) or
        None when the browser closes. `send_text(msg)` delivers a frame to the browser.
        `close(code)` closes the browser socket (1000 — normal, 4408 — idle).

        Lossless logic (ADR-012): a dedicated task reads asr-worker into a bounded
        queue; when it overflows, the browser `receive` is not called until the
        queue drains — backpressure instead of dropping samples.
        """
        doc = await self.load_for_stream(owner_id, recording_id)
        if doc is None:
            await close(CLOSE_NOT_FOUND)
            return

        phrase_id = await self.phrase_id_for(owner_id, recording_id)

        # The codec is fixed: without a working ffmpeg the "webm" object would be corrupt
        # PCM under a foreign type. Fail fast before ready — with a clear error_code.
        muxer = self._muxer_factory()
        try:
            await muxer.start()
        except MuxerUnavailable:
            logger.warning("voice_note_muxer_unavailable recording=%s", recording_id)
            await send_text(
                {
                    "type": "error",
                    "error_code": MuxerUnavailable.error_code,
                    "message": "Codec unavailable",
                }
            )
            await self._repo.set_status(
                recording_id, owner_id, status=RecordingStatus.FAILED.value,
                error_code="muxer_unavailable",
            )
            await close(CLOSE_STORAGE)
            return

        asr = self._asr_factory.connect(self._settings.asr_stream_url or "")
        try:
            await asr.open(
                recording_id=recording_id, phrase_id=phrase_id, owner_id=owner_id
            )
        except AsrStreamError as exc:
            await send_text({"type": "error", "error_code": exc.code, "message": exc.message})
            await self._repo.set_status(
                recording_id, owner_id, status=RecordingStatus.FAILED.value,
                error_code="asr_error",
            )
            await close(CLOSE_BAD_REQUEST)
            await asr.close()
            await muxer.abort()
            return
        except Exception as exc:  # noqa: BLE001 — network
            logger.warning(
                "asr_open_error recording=%s error=%s", recording_id, type(exc).__name__
            )
            await send_text(
                {
                    "type": "error",
                    "error_code": "ASR_UNAVAILABLE",
                    "message": "Recognition unavailable",
                }
            )
            await self._repo.set_status(
                recording_id, owner_id, status=RecordingStatus.FAILED.value,
                error_code="asr_error",
            )
            await close(CLOSE_BAD_REQUEST)
            await asr.close()
            await muxer.abort()
            return

        key = note_key_for(owner_id, recording_id)
        writer = MultipartWriter(self._store, key)
        try:
            await writer.open()
        except Exception as exc:  # noqa: BLE001
            await send_text(
                {
                    "type": "error",
                    "error_code": "STORAGE_UNAVAILABLE",
                    "message": "Storage unavailable",
                }
            )
            await close(CLOSE_STORAGE)
            await asr.close()
            await muxer.abort()
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE, "Storage unavailable"
            ) from exc

        await send_text(
            {"type": "ready", "recording_id": recording_id, "phrase_id": phrase_id,
             "sample_rate": 16000}
        )

        # Queue from-asr → to-browser, bounded (backpressure, ADR-012).
        pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        language: str | None = None
        got_text = False

        async def _asr_pump() -> None:
            nonlocal language, got_text
            while True:
                msg = await asr.recv()
                if msg is None:
                    await pending.put(None)
                    return
                t = msg.get("type")
                if t == "final":
                    got_text = bool((msg.get("text") or "").strip())
                    if msg.get("language"):
                        language = msg["language"]
                await pending.put(msg)

        asr_task = asyncio.create_task(_asr_pump())

        async def _forward(p: dict[str, Any]) -> None:
            await send_text(p)

        final_received = False
        # Abnormal exit (exception/cancellation) without finalization → abort (ADR-012, item 4).
        finalized = False

        try:
            while True:
                # Backpressure: while the asr-worker queue is full, we do not read the browser.
                while pending.qsize() >= pending.maxsize // 2 and not final_received:
                    await asyncio.sleep(0.01)

                recv_coro = receive()
                try:
                    frame = await asyncio.wait_for(recv_coro, timeout=30.0)
                except TimeoutError:
                    # Abandoned coroutine: close it, otherwise "never awaited" on GC.
                    recv_coro.close()
                    # No data for 30 s → close 4408 (api.md); without audio — abort.
                    await self._finish(
                        owner_id, recording_id, writer, send_text, close,
                        pending, asr, muxer, key=key, language=language,
                        got_text=got_text, close_code=CLOSE_IDLE_TIMEOUT,
                    )
                    finalized = True
                    break

                if frame is None:
                    # Socket drop: with bytes — finalize, otherwise abort (ADR-012, item 4).
                    await self._finish(
                        owner_id, recording_id, writer, send_text, close,
                        pending, asr, muxer, key=key, language=language,
                        got_text=got_text,
                    )
                    finalized = True
                    break

                if isinstance(frame, bytes):
                    # PCM → ffmpeg → WebM: only container bytes go into the object.
                    try:
                        muxed = await muxer.write(frame)
                    except MuxerError:
                        await self._fail_muxer(
                            owner_id, recording_id, writer, send_text, close, key=key
                        )
                        finalized = True
                        break
                    await writer.write_pcm(frame)
                    if muxed:
                        await writer.write(muxed)
                    await asr.send_pcm(frame)
                    # Drain ready asr frames to the browser.
                    await self._drain_pending(pending, _forward)
                    continue

                if isinstance(frame, dict) and frame.get("type") == "stop":
                    await asr.send_stop()
                    await self._finish(
                        owner_id, recording_id, writer, send_text, close,
                        pending, asr, muxer, key=key, language=language,
                        got_text=got_text,
                    )
                    finalized = True
                    break
        finally:
            asr_task.cancel()
            try:
                await asr_task
            except asyncio.CancelledError:
                pass
            await asr.close()
            if not finalized:
                # Exception/cancellation of the task: an unfinished upload must not stay open.
                await muxer.abort()
                await writer.abort()

    async def _drain_pending(
        self,
        pending: asyncio.Queue[dict[str, Any] | None],
        forward: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        while not pending.empty():
            p = pending.get_nowait()
            if p is None:
                continue
            await forward(p)

    async def _fail_muxer(
        self,
        owner_id: str,
        recording_id: str,
        writer: MultipartWriter,
        send_text: Callable[[dict[str, Any]], Awaitable[None]],
        close: Callable[[int], Awaitable[None]],
        *,
        key: str,
    ) -> None:
        """ffmpeg died mid-recording: no object, the recording goes `failed` (ADR-012, item 4)."""
        logger.warning("voice_note_muxer_failed recording=%s", recording_id)
        await writer.abort()
        await self._repo.set_status(
            recording_id, owner_id, status=RecordingStatus.FAILED.value,
            error_code="muxer_failed",
        )
        await send_text(
            {
                "type": "error",
                "error_code": MuxerError.error_code,
                "message": "Encoding error",
            }
        )
        await close(CLOSE_STORAGE)

    async def _finish(
        self,
        owner_id: str,
        recording_id: str,
        writer: MultipartWriter,
        send_text: Callable[[dict[str, Any]], Awaitable[None]],
        close: Callable[[int], Awaitable[None]],
        pending: asyncio.Queue[dict[str, Any] | None],
        asr,
        muxer: PcmMuxer,
        *,
        key: str,
        language: str | None,
        got_text: bool,
        close_code: int = CLOSE_NORMAL,
    ) -> None:
        """Reads the asr tail up to `done`, completes the object, sends stopped→done.

        Finalization is `CompleteMultipartUpload` only (ADR-012, item 5). If not a single PCM byte
        arrived — no object is created: `AbortMultipartUpload`, the recording goes `failed`
        (ADR-012, item 4; ADR takes precedence over `audio-api/api.md` §WS).
        """
        # Read the asr tail up to `done`/end.
        done_seen = False
        got_text_local = got_text
        while not done_seen:
            try:
                p = await asyncio.wait_for(pending.get(), timeout=10.0)
            except TimeoutError:
                break
            if p is None:
                break
            t = p.get("type")
            if t == "final":
                got_text_local = bool((p.get("text") or "").strip())
                if p.get("language"):
                    language = p["language"]
            await send_text(p)
            if t == "done":
                done_seen = True

        if writer.pcm_bytes == 0:
            # There was no audio: a 0-byte "playable" object is a false promise. Cancel it.
            logger.info(
                "voice_note_aborted_empty recording=%s close_code=%d",
                recording_id, close_code,
            )
            await muxer.abort()
            await writer.abort()
            await self._repo.set_status(
                recording_id, owner_id, status=RecordingStatus.FAILED.value,
                error_code="no_audio" if got_text_local else "nospeech",
            )
            await send_text(
                {
                    "type": "stopped",
                    "audio_bytes": 0,
                    "duration_ms": 0,
                    "audio_ready": False,
                }
            )
            await send_text({"type": "done"})
            await close(close_code)
            return

        duration_ms = writer.pcm_bytes // BYTES_PER_MS
        try:
            tail = await muxer.finish()
        except MuxerError:
            await self._fail_muxer(
                owner_id, recording_id, writer, send_text, close, key=key
            )
            return
        if tail:
            await writer.write(tail)
        await writer.complete()
        await self._repo.finalize_note(
            recording_id,
            owner_id,
            duration_ms=duration_ms,
            audio_bytes=writer.total_bytes,
            language=language,
            has_text=got_text_local,
        )
        # The object is closed — the voice vector is computed only from a finished object.
        await self._publish_embedding(
            owner_id, recording_id, key=key, duration_ms=duration_ms
        )
        await send_text(
            {
                "type": "stopped",
                "audio_bytes": writer.total_bytes,
                "duration_ms": duration_ms,
                "audio_ready": True,
            }
        )
        await send_text({"type": "done"})
        await close(close_code)

    async def _publish_embedding(
        self,
        owner_id: str,
        recording_id: str,
        *,
        key: str,
        duration_ms: int,
    ) -> None:
        """Publishes `audio.embedding` after `CompleteMultipartUpload`.

        A note shorter than `MIN_EMBED_SECONDS` (1 s) yields no vector: the job is not published,
        and `processing.embedding` is set to `failed` right away — the user sees an inactive
        "Make it my voice" without waiting, and `PUT /api/me/voice` answers
        `409 VOICE_NOT_READY` (us-07/init.md).

        A broker refusal does not break the note: it is already `ready` and plays (embedding is not
        a blocking property of the chat, queue-audio-embedding/message.md). Only
        recording_id and the error code go to the log: neither object keys nor phrase text.
        """
        if duration_ms < self._settings.voice_embedding_min_ms:
            logger.info(
                "embedding_skipped recording=%s reason=too_short duration_ms=%d",
                recording_id,
                duration_ms,
            )
            await self._repo.set_embedding(recording_id, owner_id, "failed")
            return
        await self._repo.set_embedding(recording_id, owner_id, "pending")
        if self._queue is None:
            # No broker: `pending` forever would mean "the menu item never comes alive".
            # Per message.md a publish refusal is `failed`, not a stuck `pending`.
            logger.warning("embedding_publish_failed recording=%s error=no_queue", recording_id)
            await self._repo.set_embedding(recording_id, owner_id, "failed")
            return
        job_id = str(uuid.uuid4())
        message: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "recording_id": recording_id,
            "owner_user_id": owner_id,
            "audio_key": key,
            "target": EMBED_TARGET_VOICE_NOTE,
            "attempt": 0,
            "created_at": _iso_now(),
        }
        try:
            self._queue.publish(
                QUEUE_EMBEDDING, message, message_id=job_id, correlation_id=recording_id
            )
        except Exception as exc:  # noqa: BLE001 — broker unavailable
            logger.warning(
                "embedding_publish_failed recording=%s error=%s",
                recording_id,
                type(exc).__name__,
            )
            await self._repo.set_embedding(recording_id, owner_id, "failed")
