"""Infrastructure: speakers and voice embedding repository (Mongo) via pymongo.

`speakers` upsert by `(recording_id, speaker_key)`; `recordings.voice_embedding` —
`$set` of two fields by owner (the only writer is diarizer).
`$setOnInsert` for `label`, `nick_id`, `is_me` and `created_at` — a redelivery
does not overwrite an assigned nick (ADR-011 / D-04).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pymongo import MongoClient

from app.domain.diarization import SpeakerSpec


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MongoSpeakerRepo:
    def __init__(self, mongo_url: str, db_name: str) -> None:
        self._client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        self._speakers = self._client[db_name]["speakers"]
        self._recordings = self._client[db_name]["recordings"]

    def upsert(self, owner_id: str, recording_id: str, spec: SpeakerSpec) -> None:
        now = _now()
        order = spec.order_index
        self._speakers.update_one(
            {"recording_id": recording_id, "speaker_key": spec.speaker_key},
            {
                "$set": {
                    "owner_user_id": owner_id,
                    "recording_id": recording_id,
                    "speaker_key": spec.speaker_key,
                    "order_index": order,
                    "centroid": spec.centroid,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "label": f"Speaker {order}",
                    "nick_id": None,
                    "is_me": False,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def set_voice_embedding(
        self,
        owner_id: str,
        recording_id: str,
        *,
        embedding: list[float],
        model: str,
    ) -> bool:
        # Only `$set` the embedding fields: `replace_one`/a whole document would wipe
        # audio-api's fields. We do NOT touch `recordings.updated_at` — per the ownership
        # map (data-model.md) only audio-api writes that field, otherwise two services race for it.
        res = self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {
                "$set": {
                    "voice_embedding": [float(v) for v in embedding],
                    "voice_embedding_model": model,
                }
            },
        )
        return res.matched_count > 0

    def close(self) -> None:
        self._client.close()
