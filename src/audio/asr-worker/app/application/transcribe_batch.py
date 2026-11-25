"""UC-A1: processing of a single `audio.transcription` job.

Order (docs/backend/asr-worker/init.md, queue-audio-transcription/message.md):
1. `schema_version != 1` → `.dead` (`unsupported_schema`), the body is not parsed.
2. owner check by the `audio_key` prefix → otherwise `.dead` (the object is not readable).
3. the `transcription.started` event.
4. check that `norm.wav` exists; missing → `.dead` (`object_not_found`).
5. split the turns into batches (up to 8 turns OR 60 s) in the original order.
6. for each batch: GPU lease (class `offline`); none → `.retry` without bumping attempt.
7. read `norm.wav` in windows (seek/range, not whole) and transcribe the batch.
8. per turn: `speaker_id` by `speaker_key`; unknown → `.dead`
   (`speaker_unknown`) + `transcription.failed`, phrases inserted so far stay.
9. upsert phrases by `(recording_id, seq)`; the `transcription.progress` event.
10. after the last batch — `transcription.completed` (with `language`). `basic_ack`.

Insertion by `seq` is idempotent: a redelivery overwrites, there are no duplicates.
OOM on a batch: the batch is halved and retried once, then `.retry`
(with a bumped attempt, up to `RABBITMQ_MAX_ATTEMPTS`, then `.dead gpu_oom`).
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from app.application.ports.asr_model import AsrModel
from app.application.ports.gpu_lease import GpuLease, LeaseDenied
from app.application.ports.json_queue import QUEUE_EVENTS
from app.config import Settings
from app.domain.transcription import (
    Phrase,
    Turn,
    build_batches,
    key_belongs_to_owner,
    merge_short_turns,
)
from app.infrastructure.parakeet_model import window_byte_range

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
GPU_CLASS = "offline"

# Actions the worker turns into ack/nack.
ACK = "ack"
NACK_RETRY = "nack_retry"
DEAD = "dead"
RETRY_WITH_ATTEMPT = "retry_with_attempt"  # (action, message) — republish with a bumped attempt


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prefix(value: str | None) -> str:
    if not value:
        return "-"
    return value[:8]


def _elapsed_ms(started: float) -> int:
    """Milliseconds since `started` (`time.monotonic()`): `*_ms` log fields are integers."""
    return int((time.monotonic() - started) * 1000)


class ObjectNotFound(RuntimeError):
    """Object missing from the bucket → `.dead (object_not_found)`."""


class SpeakerUnknown(RuntimeError):
    """Speaker not found in this recording → `.dead (speaker_unknown)`."""


class GpuOomError(RuntimeError):
    """CUDA OOM on a batch → `.retry` up to 3 attempts, then `.dead (gpu_oom)`."""


_CYR = re.compile(r"[а-яА-ЯёЁ]")
_LAT = re.compile(r"[A-Za-z]")

#: Retry windows for a text in the wrong script: first a padded one, then a 2.5 s one.
_RETRY_WINDOWS = ((600, 0), (0, 2500))


def _cyrillic_chars(text: str) -> int:
    return len(_CYR.findall(text))


def _latin_chars(text: str) -> int:
    return len(_LAT.findall(text))


def _dominant_script_is_cyrillic(texts: dict[int, str]) -> bool:
    """True when the batch speaks mostly Cyrillic — the reference for a misdetection."""
    cyr = sum(_cyrillic_chars(t or "") for t in texts.values())
    lat = sum(_latin_chars(t or "") for t in texts.values())
    return cyr > lat


def _expanded(start_ms: int, end_ms: int, pad_ms: int, min_ms: int) -> tuple[int, int]:
    """Widened window for the retry: ±`pad_ms`, and at least `min_ms` long."""
    start, end = start_ms - pad_ms, end_ms + pad_ms
    if min_ms and end - start < min_ms:
        extra = (min_ms - (end - start)) // 2
        start -= extra
        end += extra
    return max(0, start), end


class TranscribeBatchHandler:
    """Handles one queue message. Idempotent to redelivery."""

    def __init__(
        self,
        *,
        settings: Settings,
        model: AsrModel,
        store,
        repo,
        queue,
        lease: GpuLease,
        int_source=None,
    ) -> None:
        self._settings = settings
        self._model = model
        self._store = store
        self._repo = repo
        self._queue = queue
        self._lease = lease
        # Hook for interrupting a batch between turns (US-05 wires the stream here).
        # None in offline mode: batches are never interrupted.
        self._int_source = int_source

    def _scratch_dir(self, job_id: str) -> Path:
        return Path(self._settings.scratch_dir) / job_id

    def cleanup_scratch(self, job_id: str) -> None:
        shutil.rmtree(self._scratch_dir(job_id), ignore_errors=True)

    def _publish_event(
        self, event: str, *, recording_id, owner_id, job_id, data: dict
    ) -> None:
        self._queue.publish(
            QUEUE_EVENTS,
            {
                "schema_version": SCHEMA_VERSION,
                "event": event,
                "recording_id": recording_id,
                "owner_user_id": owner_id,
                "job_id": job_id,
                "at": _iso_now(),
                "data": data,
            },
            message_id=job_id,
            correlation_id=recording_id,
        )

    def _interrupted(self) -> bool:
        """True if the batch must be interrupted between turns (the stream preempts)."""
        return bool(self._int_source and self._int_source())

    def handle(self, message: dict) -> str:
        """Handles the message; returns `ack` | `nack_retry` | `dead` | retry_attempt."""
        recording_id = message.get("recording_id")
        owner_id = message.get("owner_user_id")
        job_id = message.get("job_id")
        audio_key = message.get("audio_key")
        schema_version = message.get("schema_version")

        logger.info(
            "job_start recording=%s owner=%s job=%s stage=transcription",
            recording_id,
            _prefix(owner_id),
            job_id,
        )

        # 1. Unknown schema → .dead, the body is not parsed (ADR-009).
        if schema_version != SCHEMA_VERSION:
            logger.warning(
                "unsupported_schema recording=%s version=%s", recording_id, schema_version
            )
            return DEAD

        # 2. Malformed body or a foreign object → .dead (constitution §3).
        if not recording_id or not owner_id or not audio_key or not job_id:
            logger.warning("malformed_message recording=%s", recording_id)
            return DEAD
        if not key_belongs_to_owner(audio_key, owner_id):
            logger.warning(
                "job_owner_mismatch recording=%s owner=%s", recording_id, _prefix(owner_id)
            )
            return DEAD

        # 3. Turns are mandatory and must be well-formed.
        raw_turns = message.get("turns")
        if not isinstance(raw_turns, list) or not raw_turns:
            logger.warning("no_turns recording=%s", recording_id)
            return DEAD

        self._publish_event(
            "transcription.started",
            recording_id=recording_id,
            owner_id=owner_id,
            job_id=job_id,
            data={},
        )

        # 4. The derivative must exist (ADR-014): asr-worker does not decode the source.
        if not self._store.exists(audio_key):
            logger.warning("job_object_not_found recording=%s", recording_id)
            self._publish_event(
                "transcription.failed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"error_code": "object_not_found"},
            )
            return DEAD

        # Turns: sort by start_ms and assign seq (1..N) — this is the playing order
        # in the recording, not the completion order (queue-audio-transcription/message.md).
        parsed_turns = [
            Turn(
                turn_id=t.get("turn_id", f"t{i:04d}"),
                speaker_key=t.get("speaker_key", ""),
                start_ms=int(t.get("start_ms", 0)),
                end_ms=int(t.get("end_ms", 0)),
                overlap=bool(t.get("overlap", False)),
                seq=i,
            )
            for i, t in enumerate(raw_turns, 1)
        ]
        if any(not t.speaker_key for t in parsed_turns):
            logger.warning("malformed_turns recording=%s", recording_id)
            return DEAD
        ordered = sorted(parsed_turns, key=lambda t: (t.start_ms, t.turn_id))
        # A turn of a few hundred milliseconds cannot be recognised on its own: the model
        # detects the language per window and guesses wrong (a Russian interjection comes
        # back as "Oh."). Merge such turns into their neighbours before transcribing.
        merged = merge_short_turns(ordered)
        turns = [
            Turn(
                turn_id=t.turn_id,
                speaker_key=t.speaker_key,
                start_ms=t.start_ms,
                end_ms=t.end_ms,
                overlap=t.overlap,
                seq=seq,
            )
            for seq, t in enumerate(merged, 1)
        ]

        total = len(turns)
        try:
            return self._process(
                message, turns, total, recording_id, owner_id, job_id, audio_key
            )
        except SpeakerUnknown:
            logger.warning(
                "speaker_unknown recording=%s owner=%s", recording_id, _prefix(owner_id)
            )
            self._publish_event(
                "transcription.failed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"error_code": "speaker_unknown"},
            )
            return DEAD
        except GpuOomError:
            attempt = int(message.get("attempt") or 0) + 1
            max_attempts = self._settings.rabbitmq_max_attempts
            logger.warning(
                "job_gpu_oom recording=%s attempt=%d/%d", recording_id, attempt, max_attempts
            )
            if attempt >= max_attempts:
                self._publish_event(
                    "transcription.failed",
                    recording_id=recording_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    data={"error_code": "gpu_oom"},
                )
                return DEAD
            message["attempt"] = attempt
            return RETRY_WITH_ATTEMPT

    def _process(
        self, message, turns: list[Turn], total: int, recording_id, owner_id, job_id, audio_key
    ) -> str:
        batches = build_batches(
            turns,
            max_turns=self._settings.batch_max_turns,
            max_seconds=self._settings.batch_max_seconds,
        )

        done = 0
        language: str | None = None
        # US-08: `duration_ms` (whole job) and `gpu_lease_wait_ms` (all batches) in `job_done`.
        t0 = time.monotonic()
        lease_wait_ms = 0
        for batch in batches:
            # A batch may be interrupted by the stream between turns (ADR-006 / S-06).
            # Interruption = release the lease and return to .retry without bumping attempt;
            # partially inserted batches are idempotently overwritten.
            if self._interrupted():
                return NACK_RETRY
            # GPU lease per batch. None — .retry without bumping attempt (ADR-006).
            lease_t0 = time.monotonic()
            try:
                self._lease.acquire(GPU_CLASS)
            except LeaseDenied:
                # ADR-006 follow-up: `gpu_lease_wait_ms` — how long we waited before the denial.
                logger.info(
                    "gpu_lease_wait recording=%s owner=%s stage=transcription "
                    "gpu_lease_wait_ms=%d",
                    recording_id,
                    _prefix(owner_id),
                    _elapsed_ms(lease_t0),
                )
                return NACK_RETRY
            lease_wait_ms += _elapsed_ms(lease_t0)

            hb = self._start_heartbeat()
            try:
                batch_done, batch_language = self._transcribe_batch_with_reduce(
                    batch, recording_id, owner_id, job_id, audio_key
                )
            finally:
                self._stop_heartbeat(hb)
                self._lease.release()

            done += batch_done
            language = batch_language or language
            self._publish_event(
                "transcription.progress",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"phrases_done": done, "phrases_total": total},
            )
            # The stream opened right after a batch → break before the next one.
            if self._interrupted():
                return NACK_RETRY

        self._publish_event(
            "transcription.completed",
            recording_id=recording_id,
            owner_id=owner_id,
            job_id=job_id,
            data={"phrases": total, "language": language},
        )
        logger.info(
            "job_done recording=%s phrases=%d language=%s stage=transcription "
            "duration_ms=%d gpu_lease_wait_ms=%d",
            recording_id,
            done,
            language or "-",
            _elapsed_ms(t0),
            lease_wait_ms,
        )
        return ACK

    def _transcribe_batch(
        self, batch: list[Turn], recording_id, owner_id, job_id, audio_key
    ) -> tuple[int, str | None]:
        """Transcribes one batch and upserts the phrases. Returns (n, language)."""
        language_hint = None  # The hint does not override the model detection (hf.md).

        # Read the turn windows via seek/range (not the whole file, ADR-014).
        windows: list[bytes] = []
        seqs: list[int] = []
        for turn in batch:
            start_byte, num_bytes = window_byte_range(turn.start_ms, turn.end_ms)
            windows.append(
                self._store.read_window(audio_key, start_byte=start_byte, num_bytes=num_bytes)
            )
            seqs.append(turn.seq)

        try:
            output = self._model.transcribe_windows(
                windows, seqs=seqs, language_hint=language_hint
            )
        except Exception as exc:  # noqa: BLE001
            if "out of memory" in str(exc).lower() or "CUBLAS" in str(exc):
                raise GpuOomError(str(exc)) from exc
            raise

        # A window the model cannot pin down comes back in another script ("Mm.", "Bueno.",
        # "Anyway, I think that's a good idea." in a Russian conversation): the language is
        # decided per window and a fraction of a second is not enough. Retry those with a
        # wider window — the same speech inside real context is recognised in the
        # recording's language.
        output.texts, dropped = self._retry_mismatched_script(
            output.texts, batch, audio_key, recording_id
        )

        # Resolve speaker_id BEFORE inserting the batch: unknown → SpeakerUnknown (the batch
        # is not partially written), previously inserted batches stay.
        speaker_ids: dict[int, str] = {}
        for turn in batch:
            speaker_id = self._repo.speaker_id_for(owner_id, recording_id, turn.speaker_key)
            if speaker_id is None:
                raise SpeakerUnknown(turn.speaker_key)
            speaker_ids[turn.seq] = speaker_id

        n = 0
        for turn in batch:
            text = output.texts.get(turn.seq, "").strip()
            # A window with no recognisable speech writes no phrase at all: an empty tile in
            # the chat is noise, and `n` still counts the turn as processed for the progress.
            if text:
                self._repo.upsert(
                    owner_id,
                    recording_id,
                    Phrase(
                        seq=turn.seq,
                        speaker_id=speaker_ids[turn.seq],
                        text=text,
                        start_ms=turn.start_ms,
                        end_ms=turn.end_ms,
                        overlap=turn.overlap,
                    ),
                )
            n += 1
        if dropped:
            logger.info(
                "phrases_dropped recording=%s count=%d stage=transcription", recording_id, dropped
            )
        return n, output.language

    def _retry_mismatched_script(
        self,
        texts: dict[int, str],
        batch: list[Turn],
        audio_key: str,
        recording_id,
    ) -> tuple[dict[int, str], int]:
        """Re-reads windows whose text is in the wrong script for this recording.

        The recording's language is taken from the batch itself: when most of the windows
        produced Cyrillic, a Latin-only window is a misdetection. Such a window is retried
        with a padded window and then with a 2.5 s one; the first Cyrillic result wins. A
        window that stays foreign after both attempts is dropped (returns the count) —
        storing "Bueno." in a Russian conversation is worse than storing nothing.

        Returns `(texts, dropped_count)`.
        """
        dominant_cyr = _dominant_script_is_cyrillic(texts)
        if not dominant_cyr:
            return texts, 0
        pending = [
            turn
            for turn in batch
            if (texts.get(turn.seq) or "").strip()
            and _cyrillic_chars(texts.get(turn.seq) or "") == 0
            and _latin_chars(texts.get(turn.seq) or "") > 0
        ]
        if not pending:
            return texts, 0

        retried_count = len(pending)
        result = dict(texts)
        for pad_ms, min_ms in _RETRY_WINDOWS:
            if not pending:
                break
            spans = [(_expanded(turn.start_ms, turn.end_ms, pad_ms, min_ms)) for turn in pending]
            windows = []
            for start_ms, end_ms in spans:
                start_byte, num_bytes = window_byte_range(start_ms, end_ms)
                windows.append(
                    self._store.read_window(
                        audio_key, start_byte=start_byte, num_bytes=num_bytes
                    )
                )
            retried = self._model.transcribe_windows(
                windows, seqs=[t.seq for t in pending], language_hint=None
            )
            still: list[Turn] = []
            for turn in pending:
                candidate = (retried.texts.get(turn.seq) or "").strip()
                if _cyrillic_chars(candidate) > 0:
                    result[turn.seq] = candidate
                else:
                    still.append(turn)
            pending = still

        for turn in pending:
            result[turn.seq] = ""
        logger.info(
            "language_retry recording=%s retried=%d unresolved=%d",
            recording_id,
            retried_count,
            len(pending),
        )
        return result, len(pending)

    def _transcribe_batch_with_reduce(
        self, batch: list[Turn], recording_id, owner_id, job_id, audio_key
    ) -> tuple[int, str | None]:
        """A batch with a single shrink step on OOM (queue-audio-transcription/message.md).

        OOM → halve the batch and retry ONCE (both halves without further shrinking).
        OOM again → GpuOomError propagates → `.retry` with a bumped attempt.
        """
        try:
            return self._transcribe_batch(batch, recording_id, owner_id, job_id, audio_key)
        except GpuOomError:
            if len(batch) <= 1:
                raise
            half = max(1, len(batch) // 2)
            logger.warning(
                "gpu_oom_reduce_batch recording=%s from=%d to=%d",
                recording_id,
                len(batch),
                half,
            )
            first, second = batch[:half], batch[half:]
            # Retry exactly once: the halves are transcribed WITHOUT further shrinking.
            n1, lang1 = self._transcribe_batch(first, recording_id, owner_id, job_id, audio_key)
            n2, lang2 = self._transcribe_batch(second, recording_id, owner_id, job_id, audio_key)
            return n1 + n2, lang1 or lang2

    def _start_heartbeat(self):
        """Starts the heartbeat thread for the duration of the computation; None if unsupported."""
        if hasattr(self._lease, "start_heartbeat"):
            return self._lease.start_heartbeat()  # type: ignore[attr-defined]
        return None

    def _stop_heartbeat(self, hb) -> None:
        if hb is not None and hasattr(hb, "stop"):
            hb.stop()
            hb.join(timeout=self._settings.gpu_lease_heartbeat_ms / 1000 + 1)
