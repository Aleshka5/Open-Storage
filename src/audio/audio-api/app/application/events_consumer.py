"""UC-13: `audio.events` consumer — rank-based status transitions and the stall watchdog.

Events arrive from different queues and may overtake each other. We apply an event
only if its stage is not older than the current one (audio-api/adrs.md A-06, queue-audio-events).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.application.ports.recording_repo import RecordingRepo
from app.config import Settings
from app.domain.status import RecordingStatus, can_advance

logger = logging.getLogger(__name__)

EVENT_QUEUE = "audio.events"

# event -> (target status, error_code field from data)
_EVENT_STATUS: dict[str, str] = {
    "diarization.started": RecordingStatus.DIARIZING.value,
    "diarization.completed": RecordingStatus.TRANSCRIBING.value,
    "transcription.started": RecordingStatus.TRANSCRIBING.value,
    "transcription.completed": RecordingStatus.READY.value,
}

_FAIL_EVENTS = {"diarization.failed", "transcription.failed"}

# embedding events (orthogonal to status, ADR-003/queue-audio-events):
#   processing.embedding ∈ {none,pending,ready,failed,incompatible}
_EMBEDDING_EVENTS = {"embedding.completed", "embedding.failed"}


def _prefix(value: str | None) -> str:
    """8-character prefix of the owner id for logs (we do not reveal it whole)."""
    if not value:
        return "-"
    return value[:8]


class EventsApplier:
    """Applies a single `audio.events` event to a recording."""

    def __init__(self, repo: RecordingRepo) -> None:
        self._repo = repo

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def apply(
        self, event: str, recording_id: str, owner_id: str, data: dict[str, Any]
    ) -> bool:
        """Applies the event. Returns True if the recording was found and the event was applied.

        An unknown event is idempotently ignored with a warn log (not an error).
        """
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None:
            # The recording does not belong to the owner or does not exist — leave it alone.
            logger.warning(
                "event_owner_mismatch recording=%s owner=%s", recording_id, _prefix(owner_id)
            )
            return False

        current = RecordingStatus(doc["status"])

        if event in _EVENT_STATUS:
            target = RecordingStatus(_EVENT_STATUS[event])
            if can_advance(current, target):
                # transcription.completed writes language+ready_at (queue-audio-events/message.md).
                language = data.get("language") if event == "transcription.completed" else None
                ready_at = self._now() if event == "transcription.completed" else None
                await self._repo.set_status(
                    recording_id,
                    owner_id,
                    status=target.value,
                    error_code=None,
                    language=language,
                    ready_at=ready_at,
                )
            return True

        if event in _FAIL_EVENTS:
            if can_advance(current, RecordingStatus.FAILED):
                await self._repo.set_status(
                    recording_id,
                    owner_id,
                    status=RecordingStatus.FAILED.value,
                    error_code=data.get("error_code") or "failed_media",
                )
            return True

        if event == "transcription.progress":
            phrases_done = data.get("phrases_done")
            phrases_total = data.get("phrases_total")
            if isinstance(phrases_done, int) and isinstance(phrases_total, int):
                await self._repo.set_status(
                    recording_id,
                    owner_id,
                    status=current.value,
                    error_code=None,
                    phrases_done=phrases_done,
                    phrases_total=phrases_total,
                )
            return True

        if event in _EMBEDDING_EVENTS:
            # processing.embedding — the voice-vector readiness marker, orthogonal to status.
            # completed: dim_mismatch=True → incompatible, otherwise ready.
            if event == "embedding.completed":
                dim_mismatch = bool(data.get("dim_mismatch"))
                embedding = "incompatible" if dim_mismatch else "ready"
            else:
                embedding = "failed"
            await self._repo.set_embedding(recording_id, owner_id, embedding)
            return True

        # Unknown event — ignore with a warn, do not touch the status.
        logger.warning("unknown_event event=%s recording=%s", event, recording_id)
        return True


class StallWatchdog:
    """A-06: every period, moves recordings in diarizing|transcribing without events for longer than
    PROCESSING_STALL_SECONDS to failed (stalled).
    """

    def __init__(self, repo: RecordingRepo, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    async def sweep(self) -> int:
        stalled = await self._repo.find_stalled(
            [RecordingStatus.DIARIZING.value, RecordingStatus.TRANSCRIBING.value],
            self._settings.processing_stall_seconds,
        )
        for doc in stalled:
            owner = doc.get("owner_user_id", "")
            logger.warning(
                "stall recording=%s owner=%s",
                doc.get("_id"),
                _prefix(owner),
            )
            await self._repo.mark_stalled(doc["_id"], owner)
        return len(stalled)
