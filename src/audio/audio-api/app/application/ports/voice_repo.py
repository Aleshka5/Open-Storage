"""Voice repository port (Mongo: `speakers`, `phrases`, `nicks`).

A port separate from `RecordingRepo` for UC-9/UC-10 (suggestions and nick assignment).
The only writer of the `speakers.{label,nick_id,is_me,updated_at}` fields and of
`phrases.side` is `audio-api` (data-model.md, ownership map), which is why this port lives
here and not in diarizer.
"""

from __future__ import annotations

from typing import Any, Protocol


class VoiceRepo(Protocol):
    """Access to the owner's speakers, phrases and nicks (all filtered by owner)."""

    async def get_speaker(
        self, recording_id: str, speaker_id: str, owner_id: str
    ) -> dict[str, Any] | None:
        """A recording speaker (or None if foreign/nonexistent)."""

    async def get_nick_by_id(self, nick_id: str, owner_id: str) -> dict[str, Any] | None:
        """An owner's nick by id (or None)."""

    async def find_nick_by_name_key(
        self, owner_id: str, name_key: str
    ) -> dict[str, Any] | None:
        """An owner's nick by `name_key` (or None) — for reusing a name."""

    async def create_nick(self, nick: dict[str, Any]) -> dict[str, Any]:
        """Inserts a `nicks` document; returns the created (or existing) document.

        On a conflict of the unique index `{owner_user_id, name_key}` it returns
        the existing document instead of raising (the "created first" race — see the assign flow).
        """

    async def assign_speaker(
        self,
        recording_id: str,
        speaker_id: str,
        owner_id: str,
        *,
        label: str,
        nick_id: str | None,
        is_me: bool,
    ) -> bool:
        """Writes the label onto the speaker (`label`, `nick_id`, `is_me`, `updated_at`)."""

    async def set_phrases_side(
        self, recording_id: str, speaker_id: str, owner_id: str, *, side: str
    ) -> int:
        """Rewrites `side` of all the speaker's phrases; returns `phrases_updated` (count)."""

    async def list_phrases(
        self,
        recording_id: str,
        owner_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Recording phrases with `seq > after_seq` (by `seq` ASC) + `next_after_seq`.

        The label (`label`) is joined from `speakers` by `speaker_id` (ADR-004): a phrase does not
        store the label itself. `side` defaults to `left` if there was no assignment yet.
        """

    async def create_self_speaker(
        self, recording_id: str, owner_id: str, speaker_id: str
    ) -> None:
        """Creates the note's single speaker: `speaker_key=SELF`, `order_index=1`,
        `centroid=null`, `label=Me`, `is_me=true` (data-model.md; writer — audio-api).
        """

    async def create_note_phrase(
        self,
        recording_id: str,
        owner_id: str,
        *,
        phrase_id: str,
        speaker_id: str,
    ) -> None:
        """Creates an empty note phrase: `seq=1`, `start_ms=0`, `end_ms=0`,
        `text=""`, `state=partial`, `side=right`, `overlap=false`, `revision=0`.
        """

    async def get_owner_voice(self, owner_id: str) -> dict[str, Any] | None:
        """Pointer to the owner's current "Me" voice (`owner_voices`, `_id` = owner)."""
        ...

    async def set_owner_voice(
        self,
        owner_id: str,
        *,
        recording_id: str,
        speaker_id: str | None,
        qdrant_point_id: str,
    ) -> dict[str, Any]:
        """Upsert of the `owner_voices` document (one per owner). Writer — `audio-api`."""
        ...
