"""Phrases and speakers repository (Mongo) port for asr-worker.

asr-worker owns the creation of upload phrases and the fields `text`/`state`/`revision`/
`end_ms`/`start_ms`/`seq`/`speaker_id`/`overlap`. `label`/`side` are written only by
`audio-api` (data-model.md, ownership map). A redelivery upserts by `(recording_id, seq)`:
it creates no duplicates and does not overwrite the text.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.transcription import Phrase


class PhraseRepo(Protocol):
    def upsert(self, owner_id: str, recording_id: str, phrase: Phrase) -> None:
        """Upsert a phrase by `(recording_id, seq)`.

        `$set`: owner_user_id, recording_id, seq, speaker_id, text,
        start_ms, end_ms, state=`final`, overlap, revision=0, updated_at. `$setOnInsert`:
        _id, side=`left`, created_at. Does not touch the text (same model output per window).
        """

    def speaker_id_for(self, owner_id: str, recording_id: str, speaker_key: str) -> str | None:
        """The speaker `_id` for this recording's `speaker_key`; None if the speaker is unknown."""

    # -- note stream (US-05) ---------------------------------------------------

    def get_recording(self, recording_id: str, owner_id: str) -> dict | None:
        """The recording document (for open-frame validation); None if foreign/absent."""

    def get_note_phrase(
        self, recording_id: str, owner_id: str, phrase_id: str
    ) -> dict | None:
        """The note phrase (`seq=1`) with its `speaker_id`/`side`; None if foreign/not ours.

        open-frame check: the phrase belongs to the recording, `side=right`, and its speaker
        is `is_me`.
        """

    def speaker_is_me(self, recording_id: str, owner_id: str, speaker_id: str) -> bool:
        """True if the phrase speaker is `is_me` (note: SELF)."""

    def update_stream_phrase(
        self,
        recording_id: str,
        owner_id: str,
        phrase_id: str,
        *,
        text: str,
        end_ms: int,
        state: str,
        revision: int,
    ) -> None:
        """Writes the note phrase's `text`, `end_ms`, `state`, `revision` (asr-worker writes).

        `revision` grows monotonically, `end_ms` monotonically; upsert by `(recording_id, seq=1)`.
        """
