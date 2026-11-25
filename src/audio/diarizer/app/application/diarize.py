"""UC-D1: processing of a single `audio.diarization` job.

Order (docs/backend/diarizer/api.md):
1. `schema_version != 1` → `.dead` (`unsupported_schema`), the body is not parsed.
2. owner check by the `audio_key` prefix → otherwise `.dead` (the object is not readable).
3. download the source to `SCRATCH_DIR/<job_id>/source.<ext>`.
4. ffmpeg `-ac 1 -ar 16000 -c:a pcm_s16le` → `norm.wav` (before the GPU lease, ADR-014/D-03).
5. upload `norm.wav` to the bucket (overwrite, idempotent).
6. take the GPU lease (class `offline`); none — `.retry` without bumping `attempt`.
7. Pyannote: one cluster, exclusive track, centroid per speaker.
8. upsert `speakers` by `(recording_id, speaker_key)`.
9. publish `audio.transcription` + the `diarization.completed` event.
10. `basic_ack`; scratch cleanup in `finally`.

`handle` returns the action for the channel — `ack` | `nack_retry` | `dead`. A denied lease is
`nack_retry` (not an error; `attempt` in the body is left alone). The `diarization.started`
event is emitted right after the owner check.
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.application.ports.audio_normalizer import NormalizeError
from app.application.ports.gpu_lease import GpuLease, LeaseDenied
from app.application.ports.json_queue import QUEUE_EVENTS, QUEUE_TRANSCRIPTION
from app.config import Settings
from app.domain.diarization import key_belongs_to_owner, norm_key_for, source_extension

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


class MediaFailure(RuntimeError):
    """Corrupt media / no audio track → `.dead (failed_media)`."""


class ObjectNotFound(RuntimeError):
    """Object missing from the bucket → `.dead (object_not_found)`."""


class GpuOomError(RuntimeError):
    """CUDA OOM on a file → `.retry` up to 3 attempts, then `.dead (gpu_oom)`."""


class DiarizationHandler:
    """Handles one queue message. Idempotent to redelivery."""

    def __init__(
        self,
        *,
        settings: Settings,
        model,
        store,
        repo,
        queue,
        normalizer,
        lease: GpuLease,
    ) -> None:
        self._settings = settings
        self._model = model
        self._store = store
        self._repo = repo
        self._queue = queue
        self._normalizer = normalizer
        self._lease = lease

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

    def handle(self, message: dict) -> str:
        """Handles the message; returns `ack` | `nack_retry` | `dead`."""
        recording_id = message.get("recording_id")
        owner_id = message.get("owner_user_id")
        job_id = message.get("job_id")
        audio_key = message.get("audio_key")
        schema_version = message.get("schema_version")

        logger.info(
            "job_start recording=%s owner=%s job=%s stage=diarization",
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

        self._publish_event(
            "diarization.started",
            recording_id=recording_id,
            owner_id=owner_id,
            job_id=job_id,
            data={},
        )

        scratch = self._scratch_dir(job_id)
        try:
            scratch.mkdir(parents=True, exist_ok=True)
            return self._process(message, scratch, recording_id, owner_id, job_id, audio_key)
        except MediaFailure:
            logger.warning("job_failed_media recording=%s", recording_id)
            self._publish_event(
                "diarization.failed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"error_code": "failed_media"},
            )
            return DEAD
        except ObjectNotFound:
            logger.warning("job_object_not_found recording=%s", recording_id)
            self._publish_event(
                "diarization.failed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"error_code": "object_not_found"},
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
                    "diarization.failed",
                    recording_id=recording_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    data={"error_code": "gpu_oom"},
                )
                return DEAD
            # Substantive (retryable) error: bump attempt and send back to .retry.
            message["attempt"] = attempt
            return RETRY_WITH_ATTEMPT
        finally:
            self.cleanup_scratch(job_id)

    def _process(self, message, scratch: Path, recording_id, owner_id, job_id, audio_key) -> str:
        ext = source_extension(audio_key)
        source_path = scratch / f"source.{ext}"
        norm_path = scratch / "norm.wav"

        # 3. Download the source.
        if not self._store.exists(audio_key):
            raise ObjectNotFound(audio_key)
        self._store.download(audio_key, str(source_path))

        # 4. Normalization on CPU, before the GPU lease (ADR-014 / D-03).
        try:
            self._normalizer.normalize(str(source_path), str(norm_path))
        except NormalizeError as exc:
            raise MediaFailure(str(exc)) from exc
        if not norm_path.is_file() or norm_path.stat().st_size == 0:
            raise MediaFailure("norm.wav is empty")

        # 5. Derivative to the bucket (overwrite).
        norm_key = norm_key_for(owner_id, recording_id)
        self._store.upload_file(norm_key, str(norm_path), "audio/wav")

        # 6. GPU lease. None — .retry without bumping attempt (ADR-006).
        lease_t0 = time.monotonic()
        try:
            self._lease.acquire(GPU_CLASS)
        except LeaseDenied:
            # ADR-006 follow-up: `gpu_lease_wait_ms` — how long we waited before the denial.
            logger.info(
                "gpu_lease_wait recording=%s owner=%s stage=diarization gpu_lease_wait_ms=%d",
                recording_id,
                _prefix(owner_id),
                _elapsed_ms(lease_t0),
            )
            return NACK_RETRY
        lease_wait_ms = _elapsed_ms(lease_t0)

        hb = self._start_heartbeat()
        try:
            try:
                result = self._model.diarize(str(norm_path))
            except Exception as exc:  # noqa: BLE001
                # CUDA OOM — the only "retryable" failure (queue-audio-diarization).
                if "out of memory" in str(exc).lower() or "CUBLAS" in str(exc):
                    raise GpuOomError(str(exc)) from exc
                raise

            # 7. Upsert speakers by (recording_id, speaker_key).
            for spec in result.speakers:
                self._repo.upsert(owner_id, recording_id, spec)

            # 8. Transcription job + the completed event.
            turns = [
                {
                    "turn_id": f"t{i:04d}",
                    "speaker_key": t.speaker_key,
                    "start_ms": t.start_ms,
                    "end_ms": t.end_ms,
                    "overlap": t.overlap,
                }
                for i, t in enumerate(
                    sorted(result.turns, key=lambda x: (x.start_ms, x.speaker_key)), 1
                )
            ]
            transcription_job_id = str(uuid.uuid4())
            self._queue.publish(
                QUEUE_TRANSCRIPTION,
                {
                    "schema_version": SCHEMA_VERSION,
                    "job_id": transcription_job_id,
                    "recording_id": recording_id,
                    "owner_user_id": owner_id,
                    "audio_key": norm_key,
                    "language_hint": None,
                    "turns": turns,
                    "attempt": 0,
                    "created_at": _iso_now(),
                },
                message_id=transcription_job_id,
                correlation_id=recording_id,
            )
            self._publish_event(
                "diarization.completed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={
                    "speakers": len(result.speakers),
                    "turns": len(turns),
                    "duration_ms": result.duration_ms,
                },
            )
            logger.info(
                "job_done recording=%s speakers=%d turns=%d stage=diarization "
                "duration_ms=%d gpu_lease_wait_ms=%d",
                recording_id,
                len(result.speakers),
                len(turns),
                result.duration_ms,
                lease_wait_ms,
            )
            return ACK
        finally:
            self._stop_heartbeat(hb)
            self._lease.release()

    def _start_heartbeat(self):
        """Starts the heartbeat thread for the duration of the computation; None if unsupported."""
        if hasattr(self._lease, "start_heartbeat"):
            return self._lease.start_heartbeat()  # type: ignore[attr-defined]
        return None

    def _stop_heartbeat(self, hb) -> None:
        if hb is not None and hasattr(hb, "stop"):
            hb.stop()
            hb.join(timeout=self._settings.gpu_lease_heartbeat_ms / 1000 + 1)
