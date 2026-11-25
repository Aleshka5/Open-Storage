"""Mongo: the recordings repository and idempotent index creation.

Every query carries the `owner_user_id` field in its filter (ownership invariant). Index
creation is an idempotent `create_indexes()` at startup of any service on the `audio` database.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.domain.recording import COLLECTIONS, UNIQUE_INDEX_KEYS
from app.domain.status import RecordingStatus


def _build_index_options(collection: str, keys: list[tuple[str, int]]) -> dict[str, Any]:
    opts: dict[str, Any] = {"name": "_".join(f"{k}_{d}" for k, d in keys)}
    if collection in UNIQUE_INDEX_KEYS:
        uk = UNIQUE_INDEX_KEYS[collection]
        if [k for k, _ in keys] == uk:
            opts["unique"] = True
    return opts


async def create_indexes(db: Any) -> list[str]:
    """Creates the indexes of all collections in the `audio` database (idempotently)."""
    created: list[str] = []
    for name, indexes in COLLECTIONS.items():
        coll: AsyncIOMotorCollection = db[name]
        for keys in indexes:
            opts = _build_index_options(name, keys)
            await coll.create_index(list(keys), **opts)
            created.append(f"{name}:{opts['name']}")
    return created


class MongoRecordingRepo:
    def __init__(self, db: Any) -> None:
        self._recordings: AsyncIOMotorCollection = db["recordings"]

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def insert_recording(self, recording: Any) -> None:
        doc = {
            "_id": recording.recording_id,
            "owner_user_id": recording.owner_user_id,
            "title": recording.title,
            "kind": recording.kind,
            "status": recording.status.value,
            "audio_key": recording.audio_key,
            "audio_content_type": recording.audio_content_type,
            "audio_bytes": recording.audio_bytes,
            "duration_ms": recording.duration_ms,
            "language": None,
            "is_default_voice": False,
            "voice_embedding": None,
            "voice_embedding_model": None,
            "processing": recording.default_processing(),
            "created_at": recording.created_at,
            "updated_at": recording.created_at,
            "ready_at": None,
        }
        await self._recordings.insert_one(doc)

    async def get_recording(self, recording_id: str, owner_id: str) -> dict[str, Any] | None:
        doc = await self._recordings.find_one(
            {"_id": recording_id, "owner_user_id": owner_id}
        )
        return doc

    async def list_recordings(
        self, owner_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        query: dict[str, Any] = {"owner_user_id": owner_id}
        if cursor:
            try:
                created_at_cursor = _decode_cursor(cursor)
            except (ValueError, TypeError):
                created_at_cursor = None
            if created_at_cursor:
                query["created_at"] = {"$lt": created_at_cursor}

        docs = (
            await self._recordings.find(query)
            .sort("created_at", -1)
            .limit(limit + 1)
            .to_list(length=limit + 1)
        )
        has_more = len(docs) > limit
        docs = docs[:limit]
        next_cursor = None
        if has_more and docs:
            next_cursor = _encode_cursor(docs[-1]["created_at"])
        return docs, next_cursor

    async def update_title(self, recording_id: str, owner_id: str, title: str) -> bool:
        res = await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {"$set": {"title": title, "updated_at": self._now()}},
        )
        return res.modified_count > 0 or res.matched_count > 0

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
        set_fields: dict[str, Any] = {
            "status": status,
            "updated_at": self._now(),
            "processing.updated_at": self._now(),
        }
        if error_code is not None:
            set_fields["processing.error_code"] = error_code
        if language is not None:
            set_fields["language"] = language
        if ready_at is not None:
            set_fields["ready_at"] = ready_at
        if phrases_done is not None:
            set_fields["processing.phrases_done"] = phrases_done
        if phrases_total is not None:
            set_fields["processing.phrases_total"] = phrases_total
        res = await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {"$set": set_fields},
        )
        return res.matched_count > 0

    async def find_stalled(self, statuses: list[str], stall_seconds: float) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(seconds=stall_seconds)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor = self._recordings.find(
            {
                "status": {"$in": statuses},
                "processing.updated_at": {"$lt": since_str},
            }
        )
        return await cursor.to_list(length=None)

    async def mark_stalled(self, recording_id: str, owner_id: str) -> None:
        await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {
                "$set": {
                    "status": RecordingStatus.FAILED.value,
                    "processing.error_code": "stalled",
                    "processing.updated_at": self._now(),
                    "updated_at": self._now(),
                }
            },
        )


    async def set_embedding(self, recording_id: str, owner_id: str, state: str) -> bool:
        res = await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {
                "$set": {
                    "processing.embedding": state,
                    "processing.updated_at": self._now(),
                }
            },
        )
        return res.matched_count > 0

    async def set_default_voice(
        self, recording_id: str, owner_id: str, *, is_default: bool
    ) -> None:
        await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {"$set": {"is_default_voice": is_default}},
        )

    async def clear_default_voice(self, owner_id: str, *, keep_id: str | None) -> None:
        query: dict[str, Any] = {
            "owner_user_id": owner_id,
            "is_default_voice": True,
        }
        if keep_id is not None:
            query["_id"] = {"$ne": keep_id}
        await self._recordings.update_many(query, {"$set": {"is_default_voice": False}})

    async def next_note_counter(self, owner_id: str) -> int:
        counters = self._recordings.database["counters"]
        doc = await counters.find_one_and_update(
            {"_id": f"voice_note_seq:{owner_id}"},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=True,
        )
        return int(doc["value"])

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
        set_fields: dict[str, Any] = {
            "duration_ms": duration_ms,
            "audio_bytes": audio_bytes,
            "audio_content_type": "audio/webm",
            "updated_at": self._now(),
            "processing.updated_at": self._now(),
        }
        if language is not None:
            set_fields["language"] = language
        if has_text:
            set_fields["status"] = RecordingStatus.READY.value
            set_fields["ready_at"] = self._now()
            set_fields["processing.error_code"] = None
            set_fields["processing.phrases_done"] = 1
            set_fields["processing.phrases_total"] = 1
        else:
            set_fields["status"] = RecordingStatus.FAILED.value
            set_fields["processing.error_code"] = "nospeech"
        res = await self._recordings.update_one(
            {"_id": recording_id, "owner_user_id": owner_id},
            {"$set": set_fields},
        )
        return res.matched_count > 0


def _encode_cursor(created_at: str) -> str:
    return base64.urlsafe_b64encode(created_at.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> str:
    padding = "=" * (-len(cursor) % 4)
    return base64.urlsafe_b64decode(cursor + padding).decode()


async def build_client(settings: Any) -> AsyncIOMotorClient:
    url = settings.mongo_url
    if settings.mongo_user and settings.mongo_password:
        # credentials may already be in the URL, we do not override them silently
        pass
    client = AsyncIOMotorClient(
        url,
        appname="audio-api",
        maxPoolSize=settings.mongo_max_pool_size,
        serverSelectionTimeoutMS=5000,
    )
    return client
