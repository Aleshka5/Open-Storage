"""WS `/v1/stream` handler (US-05): a live note recognition session.

Open-frame checks (asr-worker/api.md), the window buffer (StreamSession), writing the result
to Mongo (asr-worker is the writer of `phrases.text/state/revision/end_ms`), slot occupancy
and the GPU lease (ADR-006). One slot per process: a second concurrent session → `4503`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.application.ports.gpu_lease import GpuLease, LeaseDenied
from app.application.ports.phrase_repo import PhraseRepo
from app.application.stream_session import StreamModel, StreamSession
from app.config import Settings
from app.logging import forget_phrase_text, phrase_text_marker

logger = logging.getLogger(__name__)

# Close codes (asr-worker/api.md).
CLOSE_NORMAL = 1000
CLOSE_BAD_REQUEST = 4400
CLOSE_NOT_FOUND = 4404
CLOSE_IDLE_TIMEOUT = 4408
CLOSE_ALREADY_OPEN = 4409
CLOSE_GPU_BUSY = 4503

# No audio for 30 s → 4408.
IDLE_TIMEOUT_S = 30

# Internal frame buffer overflow (> 128) is a client error: 4400
# (asr-worker/api.md §Backpressure).
MAX_PENDING_FRAMES = 128

GPU_CLASS = "stream"

# Sentinels that wrap the frame iterator (see `_with_idle_timeout`).
_IDLE = object()
_OVERFLOW = object()


async def _with_idle_timeout(frame_iter, timeout_s: float, *, max_pending: int = 0):
    """Iterator wrapper: an idle `timeout_s` → `_IDLE`, a buffer > `max_pending` → `_OVERFLOW`.

    Waiting for a frame is time-bounded (4408 — "no audio for 30 s"), and the producer
    cannot outrun the consumer by more than `max_pending` frames: otherwise it is a client
    error `4400` (`asr-worker/api.md` §Backpressure) instead of memory growth. Lossless
    backpressure is stopping the socket read on the audio-api side; here we *bound* the
    internal queue rather than allow an infinite buffer.
    """
    it = frame_iter.__aiter__()
    pending: asyncio.Queue[Any] = asyncio.Queue()
    consumed = 0
    produced = 0

    async def _produce() -> None:
        nonlocal produced
        try:
            async for f in it:
                if produced - consumed > max_pending:
                    await pending.put(("over", None))
                    return
                produced += 1
                await pending.put(("frame", f))
        except Exception as exc:  # noqa: BLE001 — propagate the source exception to the consumer
            await pending.put(("error", exc))
        else:
            await pending.put(("end", None))

    task = asyncio.create_task(_produce())
    try:
        while True:
            try:
                kind, value = await asyncio.wait_for(pending.get(), timeout=timeout_s)
            except TimeoutError:
                yield _IDLE
                return
            if kind == "end":
                return
            if kind == "over":
                yield _OVERFLOW
                return
            if kind == "error":
                raise value
            consumed += 1
            yield value
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


class InvalidOpen(RuntimeError):
    """The open frame is malformed → 4400."""

    def __init__(self, close_code: int) -> None:
        super().__init__()
        self.close_code = close_code


class StreamHandler:
    """One live session. Owns the slot (one per process) and the stream GPU lease."""

    def __init__(
        self,
        *,
        settings: Settings,
        model: StreamModel,
        repo: PhraseRepo,
        lease: GpuLease,
        idle_timeout_s: float | None = None,
        max_pending_frames: int = MAX_PENDING_FRAMES,
    ) -> None:
        self._settings = settings
        self._model = model
        self._repo = repo
        self._lease = lease
        self._active = False
        # Idle timeout (4408) and frame ceiling (4400): the defaults are the contract,
        # tests inject short values.
        self._idle_timeout_s = (
            IDLE_TIMEOUT_S if idle_timeout_s is None else float(idle_timeout_s)
        )
        self._max_pending_frames = max_pending_frames
        self._close_code = CLOSE_NORMAL

    @property
    def active(self) -> bool:
        return self._active

    def validate_open(self, msg: dict[str, Any]) -> tuple[str, str, str]:
        """Validates the open frame; returns (recording_id, phrase_id, owner_id).

        Raises `InvalidOpen(close_code)`: 4400 (malformed open), 4404 (recording/phrase/
        owner/not_me), 4503 (slot/GPU busy).
        """
        if msg.get("type") != "open":
            raise InvalidOpen(CLOSE_BAD_REQUEST)
        recording_id = msg.get("recording_id")
        phrase_id = msg.get("phrase_id")
        owner_id = msg.get("owner_user_id")
        if not recording_id or not phrase_id or not owner_id:
            raise InvalidOpen(CLOSE_BAD_REQUEST)
        if msg.get("format") != "pcm_s16le" or msg.get("sample_rate") != 16000:
            raise InvalidOpen(CLOSE_BAD_REQUEST)

        recording = self._repo.get_recording(recording_id, owner_id)
        if recording is None:
            raise InvalidOpen(CLOSE_NOT_FOUND)

        phrase = self._repo.get_note_phrase(recording_id, owner_id, phrase_id)
        if phrase is None:
            raise InvalidOpen(CLOSE_NOT_FOUND)
        speaker_id = phrase.get("speaker_id")
        # The note phrase: side right, speaker is_me (asr-worker/api.md, not_me_phrase).
        if phrase.get("side") != "right" or not self._repo.speaker_is_me(
            recording_id, owner_id, speaker_id
        ):
            raise InvalidOpen(CLOSE_NOT_FOUND)

        return recording_id, phrase_id, owner_id

    def acquire_slot(self) -> None:
        """Takes the session slot + the stream GPU lease. Busy → 4503."""
        if self._active:
            raise InvalidOpen(CLOSE_GPU_BUSY)
        try:
            self._lease.acquire(GPU_CLASS)
        except LeaseDenied as exc:
            raise InvalidOpen(CLOSE_GPU_BUSY) from exc
        self._active = True

    def release_slot(self) -> None:
        if self._active:
            self._lease.release()
            self._active = False

    def make_session(self) -> StreamSession:
        return StreamSession(self._model)

    async def loop(
        self,
        recording_id: str,
        phrase_id: str,
        owner_id: str,
        *,
        receive_stream,
        send_json,
    ) -> None:
        """Drives the session: PCM → partial every 2 s, final on stop/idle, done, close 1000.

        `receive_stream` is an async iterator of frames (bytes for PCM, str for text).
        `send_json(dict)` sends a JSON frame to the client (audio-api).

        Contract closes (asr-worker/api.md): no audio for `IDLE_TIMEOUT_S` → `4408`;
        more than `MAX_PENDING_FRAMES` unprocessed frames → `4400`. Both cases still
        finalize the phrase (the text that did arrive is kept).
        """
        session = self.make_session()
        close_code = CLOSE_NORMAL
        audio_ms = 0
        session_t0 = time.monotonic()
        # US-08: `recording_id`/`job_id` in the stream are the same fields as in batches.
        logger.info(
            "stage_start stage=stream recording_id=%s job_id=%s",
            recording_id,
            phrase_id,
        )
        try:
            frames = _with_idle_timeout(
                receive_stream, self._idle_timeout_s, max_pending=self._max_pending_frames
            )
            async for frame in frames:
                if frame is _IDLE:
                    logger.info(
                        "stream_idle_timeout stage=stream recording_id=%s job_id=%s "
                        "error_code=IDLE_TIMEOUT",
                        recording_id,
                        phrase_id,
                    )
                    close_code = CLOSE_IDLE_TIMEOUT
                    break
                if frame is _OVERFLOW:
                    logger.warning(
                        "stream_frame_overflow stage=stream recording_id=%s job_id=%s "
                        "error_code=FRAME_OVERFLOW",
                        recording_id,
                        phrase_id,
                    )
                    close_code = CLOSE_BAD_REQUEST
                    break
                if isinstance(frame, str):
                    try:
                        msg = json.loads(frame)
                    except (ValueError, TypeError):
                        msg = {}
                    if msg.get("type") == "stop":
                        break
                    continue
                if isinstance(frame, (bytes, bytearray)):
                    session.feed(bytes(frame))
                if session.should_emit_partial():
                    text, end_ms, revision = session.transcribe()
                    # US-08: the recognized text must not reach the log even by
                    # accident (free-form msg) — register it with the process.
                    phrase_text_marker(text)
                    # The chat reads phrases by poll (ADR-003, S-03). A partial that
                    # only travels on the socket leaves the tile empty until `final`.
                    self._repo.update_stream_phrase(
                        recording_id,
                        owner_id,
                        phrase_id,
                        text=text,
                        end_ms=end_ms,
                        state="partial",
                        revision=revision,
                    )
                    await send_json(
                        {
                            "type": "partial",
                            "phrase_id": phrase_id,
                            "text": text,
                            "end_ms": end_ms,
                            "revision": revision,
                        }
                    )
            text, end_ms, revision, lang = session.finalize()
            phrase_text_marker(text)
            audio_ms = end_ms
            await send_json(
                {
                    "type": "final",
                    "phrase_id": phrase_id,
                    "text": text,
                    "end_ms": end_ms,
                    "revision": revision,
                    "language": lang,
                }
            )
            # Persist the final phrase: asr-worker is the writer of text/state/revision/end_ms.
            self._repo.update_stream_phrase(
                recording_id,
                owner_id,
                phrase_id,
                text=text,
                end_ms=end_ms,
                state="final",
                revision=revision,
            )
            # The phrase text is NOT logged here: only the duration in ms (US-08, item 4).
            logger.info(
                "stage_done stage=stream recording_id=%s job_id=%s duration_ms=%d "
                "error_code=%s",
                recording_id,
                phrase_id,
                int((time.monotonic() - session_t0) * 1000),
                "NONE" if close_code == CLOSE_NORMAL else str(close_code),
            )
            await send_json({"type": "done", "audio_ms": audio_ms})
        except Exception as exc:  # noqa: BLE001 — do not crash the stream process
            logger.warning(
                "stream_loop_error stage=stream recording_id=%s job_id=%s error=%s",
                recording_id,
                phrase_id,
                type(exc).__name__,
            )
            close_code = CLOSE_BAD_REQUEST
            raise
        finally:
            # The registry does not grow: this recording's texts are no longer needed.
            forget_phrase_text(text)
            self.release_slot()
            self._close_code = close_code

    @property
    def close_code(self) -> int:
        """Socket close code after `loop` (1000 / 4400 / 4408)."""
        return self._close_code
