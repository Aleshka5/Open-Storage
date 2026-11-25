"""Domain: the recording entity (Recording) and the Mongo index map.

The domain knows the owner_user_id field, the ownership invariants and the index layout, but
not MinIO/Mongo/Qdrant as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.status import RecordingStatus

# Index set of every collection in the `audio` database — part of the read contract
# (docs/backend/data-model.md). Created by the idempotent create_indexes() at startup.
RECORDINGS_INDEXES: list[list[tuple[str, int]]] = [
    [("owner_user_id", 1), ("created_at", -1)],
    [("owner_user_id", 1), ("kind", 1), ("is_default_voice", 1)],
    [("status", 1), ("processing.updated_at", 1)],
]

SPEAKERS_INDEXES: list[list[tuple[str, int]]] = [
    [("recording_id", 1), ("order_index", 1)],
    [("owner_user_id", 1), ("recording_id", 1)],
]

PHRASES_INDEXES: list[list[tuple[str, int]]] = [
    [("recording_id", 1), ("seq", 1)],
    [("owner_user_id", 1), ("recording_id", 1), ("start_ms", 1)],
    [("recording_id", 1), ("start_ms", 1)],
]

NICKS_INDEXES: list[list[tuple[str, int]]] = [
    [("owner_user_id", 1), ("name_key", 1)],
]

OWNER_VOICES_INDEXES: list[list[tuple[str, int]]] = []

# Unique indexes are declared by a separate key map.
UNIQUE_INDEX_KEYS: dict[str, list[str]] = {
    "speakers": ["recording_id", "order_index"],
    "phrases": ["recording_id", "seq"],
    "nicks": ["owner_user_id", "name_key"],
}

# The five collections of the `audio` database and their indexes.
COLLECTIONS: dict[str, list[list[tuple[str, int]]]] = {
    "recordings": RECORDINGS_INDEXES,
    "speakers": SPEAKERS_INDEXES,
    "phrases": PHRASES_INDEXES,
    "nicks": NICKS_INDEXES,
    "owner_voices": OWNER_VOICES_INDEXES,
}


@dataclass
class Recording:
    """A recording in its product form. The fields are written by `audio-api` (ownership map)."""

    recording_id: str
    owner_user_id: str
    title: str
    kind: str = "upload"
    status: RecordingStatus = RecordingStatus.UPLOADED
    audio_key: str | None = None
    audio_content_type: str | None = None
    audio_bytes: int = 0
    duration_ms: int | None = None
    language: str | None = None
    is_default_voice: bool = False
    voice_embedding: Any = None
    voice_embedding_model: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    ready_at: str | None = None
    processing: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.recording_id

    def default_processing(self) -> dict[str, Any]:
        return {
            "error_code": None,
            "phrases_done": 0,
            "phrases_total": 0,
            "embedding": "none",
            "updated_at": self.created_at,
        }


def owner_prefix(owner_id: str) -> str:
    """Ownership prefix for MinIO keys: `u/{owner}/`."""
    return f"u/{owner_id}/"


def audio_key_for(owner_id: str, recording_id: str, ext: str) -> str:
    """Object key `original.{ext}` per the MinIO contract."""
    return f"{owner_prefix(owner_id)}rec/{recording_id}/original.{ext}"


def note_key_for(owner_id: str, recording_id: str) -> str:
    """Voice note object key `note.webm` (bucket-and-keys.md)."""
    return f"{owner_prefix(owner_id)}rec/{recording_id}/note.webm"


# Marker of the voice note "Me" speaker (data-model.md).
SELF_SPEAKER_KEY = "SELF"
