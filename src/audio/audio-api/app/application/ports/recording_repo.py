"""Recording repository port (Mongo)."""
from __future__ import annotations

from typing import Any, Protocol

from app.domain.recording import Recording


class RecordingRepo(Protocol):
    """Access to the collections of the `audio` database. Every query is filtered by owner."""

    async def insert_recording(self, recording: Recording) -> None:
        ...

    async def get_recording(self, recording_id: str, owner_id: str) -> dict[str, Any] | None:
        ...

    async def list_recordings(
        self, owner_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        ...

    async def update_title(self, recording_id: str, owner_id: str, title: str) -> bool:
        ...

    async def set_status(
        self,
        recording_id: str,
        owner_id: str,
        *,
        status: str,
        error_code: str | None,
        language: str | None = None,
        ready_at: str | None = None,
        phrases_done: int | None = None,
        phrases_total: int | None = None,
    ) -> bool:
        ...

    async def find_stalled(
        self, statuses: list[str], stall_seconds: float
    ) -> list[dict[str, Any]]:
        ...

    async def mark_stalled(self, recording_id: str, owner_id: str) -> None:
        ...

    async def set_embedding(self, recording_id: str, owner_id: str, state: str) -> bool:
        ...

    async def next_note_counter(self, owner_id: str) -> int:
        """Atomically increments the "Note N" counter and returns the new number.

        The document is `counters._id = voice_note_seq:{owner}`; `findOneAndUpdate` + `$inc`
        (data-model.md). The number grows monotonically and is never reused.
        """
        ...

    async def set_default_voice(
        self, recording_id: str, owner_id: str, *, is_default: bool
    ) -> None:
        """Sets/clears `recordings.is_default_voice` (exactly one `true` per owner).

        The writer is `audio-api` (data-model.md). Clearing it from the old note is done by
        `clear_default_voice`, not by this method: here one field changes, so as not to
        touch `updated_at` and not to affect other people's recordings.
        """
        ...

    async def clear_default_voice(self, owner_id: str, *, keep_id: str | None) -> None:
        """Clears `is_default_voice` from all of the owner's notes except `keep_id`.

        Called before setting a new voice (ADR-008: "exactly one `true`");
        `keep_id=None` clears it from all.
        """
        ...

    async def finalize_note(
        self,
        recording_id: str,
        owner_id: str,
        *,
        duration_ms: int,
        audio_bytes: int,
        language: str | None,
        has_text: bool,
    ) -> bool:
        """Finalizes the note: `ready` (has text) or `failed nospeech`; prepares the audio.

        Writes `audio_content_type`, `audio_bytes`, `duration_ms`, `language`, `ready_at`
        and `status`. The object is already completed in MinIO (CompleteMultipartUpload) beforehand.
        """
        ...
