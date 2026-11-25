"""Infrastructure: the voice repository (Mongo `speakers`, `phrases`, `nicks`).

Implements the `VoiceRepo` port for UC-9/UC-10. Every query carries the owner_user_id field in
its filter (ownership invariant). Assignment is idempotent: a repeated `update` yields the same
state (ADR-011, no transactions — the "speaker → phrase side" order is valid at every
step).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.domain.app_error import AppError
from app.domain.errors import ErrorCode


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MongoVoiceRepo:
    def __init__(self, db: Any) -> None:
        self._speakers: AsyncIOMotorCollection = db["speakers"]
        self._phrases: AsyncIOMotorCollection = db["phrases"]
        self._nicks: AsyncIOMotorCollection = db["nicks"]
        self._owner_voices: AsyncIOMotorCollection = db["owner_voices"]

    async def get_speaker(
        self, recording_id: str, speaker_id: str, owner_id: str
    ) -> dict[str, Any] | None:
        return await self._speakers.find_one(
            {
                "_id": speaker_id,
                "recording_id": recording_id,
                "owner_user_id": owner_id,
            }
        )

    async def get_nick_by_id(self, nick_id: str, owner_id: str) -> dict[str, Any] | None:
        return await self._nicks.find_one(
            {"_id": nick_id, "owner_user_id": owner_id}
        )

    async def find_nick_by_name_key(
        self, owner_id: str, name_key: str
    ) -> dict[str, Any] | None:
        return await self._nicks.find_one(
            {"owner_user_id": owner_id, "name_key": name_key}
        )

    async def create_nick(self, nick: dict[str, Any]) -> dict[str, Any]:
        # Uniqueness of owner+name_key is held by the index (data-model.md). In a race of two
        # parallel creations one name yields one document: on E11000 we return
        # the existing one instead of raising.
        try:
            await self._nicks.insert_one(nick)
        except Exception as exc:  # noqa: BLE001
            existing = await self._nicks.find_one(
                {
                    "owner_user_id": nick["owner_user_id"],
                    "name_key": nick["name_key"],
                }
            )
            if existing is not None:
                return existing
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE, "Storage unavailable"
            ) from exc
        # Return the inserted document (with name/name_key, as the caller asked).
        return dict(nick)

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
        res = await self._speakers.update_one(
            {
                "_id": speaker_id,
                "recording_id": recording_id,
                "owner_user_id": owner_id,
            },
            {
                "$set": {
                    "label": label,
                    "nick_id": nick_id,
                    "is_me": is_me,
                    "updated_at": _now(),
                }
            },
        )
        return res.matched_count > 0

    async def set_phrases_side(
        self, recording_id: str, speaker_id: str, owner_id: str, *, side: str
    ) -> int:
        res = await self._phrases.update_many(
            {
                "recording_id": recording_id,
                "speaker_id": speaker_id,
                "owner_user_id": owner_id,
            },
            {"$set": {"side": side}},
        )
        return res.modified_count

    async def list_phrases(
        self,
        recording_id: str,
        owner_id: str,
        *,
        after_seq: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Recording phrases with `seq > after_seq` + labels from `speakers` (ADR-004)."""
        phrase_docs = (
            await self._phrases.find(
                {
                    "recording_id": recording_id,
                    "owner_user_id": owner_id,
                    "seq": {"$gt": after_seq},
                }
            )
            .sort("seq", 1)
            .limit(limit)
            .to_list(length=limit)
        )

        # Labels of the recording's speakers: speaker_id -> label (frozen label, ADR-004).
        speaker_ids = [p.get("speaker_id") for p in phrase_docs if p.get("speaker_id")]
        labels: dict[str, str] = {}
        if speaker_ids:
            speaker_docs = await self._speakers.find(
                {
                    "recording_id": recording_id,
                    "owner_user_id": owner_id,
                    "_id": {"$in": speaker_ids},
                },
                {"_id": 1, "label": 1},
            ).to_list(length=len(speaker_ids))
            labels = {s["_id"]: s.get("label", "Speaker") for s in speaker_docs}

        items: list[dict[str, Any]] = []
        next_after_seq = after_seq
        for p in phrase_docs:
            seq = p.get("seq")
            items.append(
                {
                    "id": p.get("_id"),
                    "seq": seq,
                    "speaker_id": p.get("speaker_id"),
                    "label": labels.get(p.get("speaker_id")),
                    "side": p.get("side", "left"),
                    "start_ms": p.get("start_ms"),
                    "end_ms": p.get("end_ms"),
                    "text": p.get("text"),
                    "state": p.get("state", "final"),
                    "revision": p.get("revision", 0),
                    "overlap": p.get("overlap", False),
                }
            )
            next_after_seq = max(next_after_seq, seq or 0)

        return items, next_after_seq

    async def create_self_speaker(
        self, recording_id: str, owner_id: str, speaker_id: str
    ) -> None:
        await self._speakers.insert_one(
            {
                "_id": speaker_id,
                "owner_user_id": owner_id,
                "recording_id": recording_id,
                "speaker_key": "SELF",
                "order_index": 1,
                "centroid": None,
                "label": "Me",
                "nick_id": None,
                "is_me": True,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )

    async def create_note_phrase(
        self,
        recording_id: str,
        owner_id: str,
        *,
        phrase_id: str,
        speaker_id: str,
    ) -> None:
        await self._phrases.insert_one(
            {
                "_id": phrase_id,
                "owner_user_id": owner_id,
                "recording_id": recording_id,
                "speaker_id": speaker_id,
                "seq": 1,
                "start_ms": 0,
                "end_ms": 0,
                "text": "",
                "side": "right",
                "state": "partial",
                "overlap": False,
                "revision": 0,
                "created_at": _now(),
                "updated_at": _now(),
            }
        )

    async def get_owner_voice(self, owner_id: str) -> dict[str, Any] | None:
        return await self._owner_voices.find_one({"_id": owner_id})

    async def set_owner_voice(
        self,
        owner_id: str,
        *,
        recording_id: str,
        speaker_id: str | None,
        qdrant_point_id: str,
    ) -> dict[str, Any]:
        # One document per owner (`_id` = owner): replacing the voice rewrites the pointer,
        # a second "Me" never appears in Mongo (ADR-008, data-model.md §owner_voices).
        doc = {
            "_id": owner_id,
            "recording_id": recording_id,
            "speaker_id": speaker_id,
            "qdrant_point_id": qdrant_point_id,
            "updated_at": _now(),
        }
        await self._owner_voices.update_one(
            {"_id": owner_id}, {"$set": doc}, upsert=True
        )
        return doc
