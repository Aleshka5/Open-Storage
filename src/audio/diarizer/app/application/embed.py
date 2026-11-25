"""UC-D2: processing of a single `audio.embedding` job — the note's voice embedding.

Order (docs/backend/diarizer/api.md §Input: `audio.embedding`):

1. `schema_version != 1` → `.dead` (`unsupported_schema`), the body is not parsed (ADR-009).
2. owner check by the `audio_key` prefix → otherwise `.dead` (the object is not readable).
3. download `note.webm` to `SCRATCH_DIR/<job_id>/source.<ext>`; object missing — `.dead`
   (`object_not_found`), the `embedding.failed` event.
4. decode to 16 kHz mono (`ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le`, ADR-014) — on CPU.
5. duration < `MIN_EMBED_SECONDS` (1 s) → the `embedding.failed (too_short)` event,
   `.dead`; `voice_embedding` stays `null` (queue-audio-embedding/message.md).
6. GPU lease of class `interactive` (above diarization); none — `.retry` without bumping `attempt`.
7. **one** embedding over the whole file (not an average over phrases) with the same model that
   produces the centroids (ADR-007).
8. `$set recordings.{voice_embedding, voice_embedding_model}` — the only writer.
9. the `embedding.completed {dim, dim_mismatch}` event; `dim_mismatch` — the dimension is not
   the collection's, the product writes `VOICE_INDEX_INCOMPATIBLE`.

We must get back to the `interactive` lease class quickly: diarization grabs the same
`gpu:lease`, so we hold the lease only for the inference, decoding happens before it.
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.application.ports.audio_normalizer import NormalizeError
from app.application.ports.gpu_lease import GpuLease, LeaseDenied
from app.application.ports.json_queue import QUEUE_EMBEDDING, QUEUE_EVENTS
from app.config import Settings
from app.domain.diarization import CENTROID_DIM, key_belongs_to_owner, source_extension

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# Lease class: the voice embedding is needed by the time the user taps "Make this my
# voice", so it ranks above `offline` diarization but does not preempt the stream (ADR-006).
GPU_CLASS = "interactive"

# Actions for the channel (same as UC-D1).
ACK = "ack"
NACK_RETRY = "nack_retry"
DEAD = "dead"
RETRY_WITH_ATTEMPT = "retry_with_attempt"

# `embedding.failed` reason for a too-short note (message.md §Errors).
REASON_TOO_SHORT = "too_short"
REASON_OBJECT_NOT_FOUND = "object_not_found"


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prefix(value: str | None) -> str:
    if not value:
        return "-"
    return value[:8]


class ObjectNotFound(RuntimeError):
    """Object missing from the bucket → `.dead (object_not_found)`."""


class GpuOomError(RuntimeError):
    """CUDA OOM during embedding → `.retry` up to 3 attempts, then `.dead (gpu_oom)`."""


class EmbeddingHandler:
    """One vector per note. Idempotent to redelivery (the `$set` overwrites)."""

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

    @property
    def min_embed_ms(self) -> int:
        """`MIN_EMBED_SECONDS` in milliseconds — from configuration, a single product constant."""
        return int(self._settings.min_embed_seconds * 1000)

    def _scratch_dir(self, job_id: str) -> Path:
        return Path(self._settings.scratch_dir) / job_id

    def cleanup_scratch(self, job_id: str) -> None:
        shutil.rmtree(self._scratch_dir(job_id), ignore_errors=True)

    def _publish_event(self, event: str, *, recording_id, owner_id, job_id, data: dict) -> None:
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

    def _dead(self, message: dict, *, recording_id, owner_id, job_id, reason: str) -> str:
        """Substantive error: the `embedding.failed` event + the body straight to `.dead`.

        nack(requeue=false) would return the message to `.retry` and it would spin forever —
        so the body is published to `.dead` and the original is acked (ADR-009).
        """
        self._publish_event(
            "embedding.failed",
            recording_id=recording_id,
            owner_id=owner_id,
            job_id=job_id,
            data={"error_code": reason},
        )
        publish_dead = getattr(self._queue, "publish_dead", None)
        if publish_dead is not None:
            publish_dead(QUEUE_EMBEDDING, message)
        return DEAD

    def handle(self, message: dict) -> str:
        """Handles the message; `ack` | `nack_retry` | `dead` | `retry_with_attempt`."""
        recording_id = message.get("recording_id")
        owner_id = message.get("owner_user_id")
        job_id = message.get("job_id")
        audio_key = message.get("audio_key")
        schema_version = message.get("schema_version")

        logger.info(
            "embed_job_start recording=%s owner=%s job=%s",
            recording_id,
            _prefix(owner_id),
            job_id,
        )

        if schema_version != SCHEMA_VERSION:
            logger.warning(
                "unsupported_schema recording=%s version=%s", recording_id, schema_version
            )
            return DEAD
        if not recording_id or not owner_id or not audio_key or not job_id:
            logger.warning("malformed_message recording=%s", recording_id)
            return DEAD
        if not key_belongs_to_owner(audio_key, owner_id):
            # A foreign object is not read and we do not pay a retry for it (constitution §3).
            logger.warning(
                "embed_job_owner_mismatch recording=%s owner=%s",
                recording_id,
                _prefix(owner_id),
            )
            return DEAD

        scratch = self._scratch_dir(job_id)
        try:
            scratch.mkdir(parents=True, exist_ok=True)
            return self._process(message, scratch, recording_id, owner_id, job_id, audio_key)
        except ObjectNotFound:
            logger.warning("embed_object_not_found recording=%s", recording_id)
            return self._dead(
                message,
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                reason=REASON_OBJECT_NOT_FOUND,
            )
        except GpuOomError:
            attempt = int(message.get("attempt") or 0) + 1
            max_attempts = self._settings.rabbitmq_max_attempts
            logger.warning(
                "embed_gpu_oom recording=%s attempt=%d/%d", recording_id, attempt, max_attempts
            )
            if attempt >= max_attempts:
                self._publish_event(
                    "embedding.failed",
                    recording_id=recording_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    data={"error_code": "gpu_oom"},
                )
                return self._dead(
                    message,
                    recording_id=recording_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    reason="gpu_oom",
                )
            message["attempt"] = attempt
            return RETRY_WITH_ATTEMPT
        finally:
            self.cleanup_scratch(job_id)

    def _process(self, message, scratch: Path, recording_id, owner_id, job_id, audio_key) -> str:
        ext = source_extension(audio_key)
        source_path = scratch / f"source.{ext}"
        norm_path = scratch / "norm.wav"

        if not self._store.exists(audio_key):
            raise ObjectNotFound(audio_key)
        self._store.download(audio_key, str(source_path))

        # Decoding on CPU before the GPU lease: the lease covers a single inference.
        try:
            self._normalizer.normalize(str(source_path), str(norm_path))
        except NormalizeError as exc:
            logger.warning("embed_media_failed recording=%s", recording_id)
            self._publish_event(
                "embedding.failed",
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                data={"error_code": "failed_media"},
            )
            raise ObjectNotFound(audio_key) from exc

        duration_ms = self._normalizer.probe_duration_ms(str(norm_path)) or 0
        if duration_ms < self.min_embed_ms:
            # MIN_EMBED_SECONDS: a short signal is not a voice, no vector is written (message.md).
            logger.info(
                "embed_too_short recording=%s duration_ms=%d", recording_id, duration_ms
            )
            return self._dead(
                message,
                recording_id=recording_id,
                owner_id=owner_id,
                job_id=job_id,
                reason=REASON_TOO_SHORT,
            )

        try:
            self._lease.acquire(GPU_CLASS)
        except LeaseDenied:
            logger.info(
                "embed_gpu_lease_wait recording=%s owner=%s", recording_id, _prefix(owner_id)
            )
            return NACK_RETRY

        hb = self._start_heartbeat()
        try:
            try:
                vector = self._model.embed(str(norm_path))
            except Exception as exc:  # noqa: BLE001
                if "out of memory" in str(exc).lower() or "CUBLAS" in str(exc):
                    raise GpuOomError(str(exc)) from exc
                logger.warning(
                    "embed_model_failed recording=%s error=%s",
                    recording_id,
                    type(exc).__name__,
                )
                self._publish_event(
                    "embedding.failed",
                    recording_id=recording_id,
                    owner_id=owner_id,
                    job_id=job_id,
                    data={"error_code": "embedding_failed"},
                )
                raise ObjectNotFound(audio_key) from exc
        finally:
            self._stop_heartbeat(hb)
            self._lease.release()

        dim = len(vector)
        dim_mismatch = dim != CENTROID_DIM
        if dim_mismatch:
            # The vector is written anyway: the product decides (VOICE_INDEX_INCOMPATIBLE).
            logger.warning(
                "embed_dim_mismatch recording=%s dim=%d expected=%d",
                recording_id,
                dim,
                CENTROID_DIM,
            )
        self._repo.set_voice_embedding(
            owner_id, recording_id, embedding=vector, model=self._model.model_id
        )
        self._publish_event(
            "embedding.completed",
            recording_id=recording_id,
            owner_id=owner_id,
            job_id=job_id,
            data={"dim": dim, "dim_mismatch": dim_mismatch, "duration_ms": duration_ms},
        )
        logger.info(
            "embed_job_done recording=%s dim=%d duration_ms=%d", recording_id, dim, duration_ms
        )
        return ACK

    def _start_heartbeat(self):
        if hasattr(self._lease, "start_heartbeat"):
            return self._lease.start_heartbeat()  # type: ignore[attr-defined]
        return None

    def _stop_heartbeat(self, hb) -> None:
        if hb is not None and hasattr(hb, "stop"):
            hb.stop()
            hb.join(timeout=self._settings.gpu_lease_heartbeat_ms / 1000 + 1)
