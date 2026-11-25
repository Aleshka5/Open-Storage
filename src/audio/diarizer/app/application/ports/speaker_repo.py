"""Speakers repository (Mongo `speakers`) port for diarizer.

diarizer owns the creation of upload speakers and the centroids; `label`/`nick_id`/`is_me`
are written only by `audio-api` (data-model.md, ownership map). A redelivery upserts
by `(recording_id, speaker_key)`: it creates no duplicates and does not overwrite the nick.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.diarization import SpeakerSpec


class SpeakerRepo(Protocol):
    def upsert(self, owner_id: str, recording_id: str, spec: SpeakerSpec) -> None:
        """Upsert a speaker by `(recording_id, speaker_key)`.

        `$set`: centroid, order_index, owner, recording_id, speaker_key, updated_at.
        `$setOnInsert`: label (`Speaker {order_index}`), nick_id=null, is_me=false,
        created_at. Never touches label/nick_id/is_me on a repeat (ADR / D-04).
        """

    def set_voice_embedding(
        self,
        owner_id: str,
        recording_id: str,
        *,
        embedding: list[float],
        model: str,
    ) -> bool:
        """Writes `recordings.{voice_embedding, voice_embedding_model}` (data-model.md).

        The only writer of these fields is `diarizer`. `$set` of two fields of a specific
        recording of the owner; `replace_one` on `recordings` is never used so as not to
        lose the other fields (diarizer/api.md §audio.embedding). A redelivery
        overwrites the value — idempotent. False — the recording was not found/is foreign.
        """
