"""Infrastructure: phrases and speakers repository (Mongo `phrases`/`speakers`), synchronous.

Upsert phrases by `(recording_id, seq)`. `side` is not written: its owner is `audio-api`
(nick/Me assignment, ADR-004/011; data-model "one writer per field"). The owner is in
every query: the owner filter (constitution §3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pymongo import MongoClient

from app.domain.transcription import Phrase


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MongoPhraseRepo:
    def __init__(self, mongo_url: str, db_name: str) -> None:
        self._client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        self._phrases = self._client[db_name]["phrases"]
        self._speakers = self._client[db_name]["speakers"]
        self._recordings = self._client[db_name]["recordings"]

    def upsert(self, owner_id: str, recording_id: str, phrase: Phrase) -> None:
        now = _now()
        self._phrases.update_one(
            {"recording_id": recording_id, "seq": phrase.seq},
            {
                "$set": {
                    "owner_user_id": owner_id,
                    "recording_id": recording_id,
                    "seq": phrase.seq,
                    "speaker_id": phrase.speaker_id,
                    "text": phrase.text,
                    "start_ms": phrase.start_ms,
                    "end_ms": phrase.end_ms,
                    "state": "final",
                    "overlap": phrase.overlap,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "revision": 0,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def speaker_id_for(self, owner_id: str, recording_id: str, speaker_key: str) -> str | None:
        doc = self._speakers.find_one(
            {
                "owner_user_id": owner_id,
                "recording_id": recording_id,
                "speaker_key": speaker_key,
            },
            {"_id": 1},
        )
        return doc["_id"] if doc else None

    # -- note stream (US-05) ---------------------------------------------------

    def get_recording(self, recording_id: str, owner_id: str) -> dict | None:
        return self._recordings.find_one(
            {"_id": recording_id, "owner_user_id": owner_id}
        )

    def get_note_phrase(self, recording_id: str, owner_id: str, phrase_id: str) -> dict | None:
        return self._phrases.find_one(
            {
                "_id": phrase_id,
                "recording_id": recording_id,
                "owner_user_id": owner_id,
            }
        )

    def speaker_is_me(self, recording_id: str, owner_id: str, speaker_id: str) -> bool:
        doc = self._speakers.find_one(
            {
                "_id": speaker_id,
                "recording_id": recording_id,
                "owner_user_id": owner_id,
            },
            {"is_me": 1},
        )
        return bool(doc and doc.get("is_me") is True)

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
        # Monotonic revision: never roll back to a lower one (a late duplicate from a batch).
        self._phrases.update_one(
            {"_id": phrase_id, "recording_id": recording_id,
             "owner_user_id": owner_id},
            {
                "$set": {
                    "text": text,
                    "end_ms": end_ms,
                    "state": state,
                    "revision": revision,
                    "updated_at": _now(),
                }
            },
        )

    def close(self) -> None:
        self._client.close()
