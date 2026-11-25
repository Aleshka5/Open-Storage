"""Domain: recording statuses and transition rules.

The single source of truth about status ranks and their transitions. Infrastructure and
presentation do not leak in here.
"""

from __future__ import annotations

from enum import StrEnum


class RecordingStatus(StrEnum):
    """Recording statuses."""

    UPLOADED = "uploaded"
    DIARIZING = "diarizing"
    TRANSCRIBING = "transcribing"
    READY = "ready"
    FAILED = "failed"
    # Voice note (US-05): does not follow the upload->transcribing->ready scale,
    # does not receive audio.events events — audio-api drives the status itself.
    RECORDING = "recording"
    FINALIZING = "finalizing"


# Rank for the monotonic scale: uploaded(0) -> diarizing(1) -> transcribing(2) -> ready(3).
_RANK: dict[RecordingStatus, int] = {
    RecordingStatus.UPLOADED: 0,
    RecordingStatus.DIARIZING: 1,
    RecordingStatus.TRANSCRIBING: 2,
    RecordingStatus.READY: 3,
}


def status_rank(status: RecordingStatus) -> int:
    """Status rank: -1 for `failed`, otherwise 0..3."""
    if status is RecordingStatus.FAILED:
        return -1
    return _RANK[status]


def is_terminal(status: RecordingStatus) -> bool:
    return status in (RecordingStatus.READY, RecordingStatus.FAILED)


def can_advance(current: RecordingStatus, incoming: RecordingStatus) -> bool:
    """Whether an event of rank `incoming` may be applied on top of `current`.

    `failed` is terminal and applies from any non-ready state; the others — only
    forward along the scale. A late duplicate (rank <= current) does not roll the status back.
    """
    if incoming is RecordingStatus.FAILED:
        return current is not RecordingStatus.READY
    return _RANK[incoming] > _RANK[current]


# Statuses watched by the stall watchdog.
STALL_WATCH_STATUSES: tuple[RecordingStatus, ...] = (
    RecordingStatus.DIARIZING,
    RecordingStatus.TRANSCRIBING,
)
