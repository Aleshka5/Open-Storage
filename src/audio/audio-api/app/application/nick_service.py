"""UC-9 scenarios (suggestions) and UC-10 (nick assignment / creation / "Me").

Invariants (constitution §3, §6; ADR-007/008/011):
- The speaker centroid is the only query vector; it is not recomputed here.
- `centroid is None` (speaker without an embedding) → no suggestions (`items: []`), not a crash
  and not a silent search over zeros (ADR-007, diarizer returns `None`, not a zero vector).
- Assignment is idempotent: the same nick again → `200` unchanged; a different nick for an
  already assigned speaker → `409 ASSIGNMENT_LOCKED`.
- The nick is always written to Mongo; the Qdrant point is best-effort (with Qdrant down the nick
  is still created, `voice_index_write_failed` goes to the log, suggestions won't see it — ADR-008).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.application.ports.voice_index import (
    VoiceIndex,
    VoiceIndexUnavailable,
)
from app.application.ports.voice_repo import VoiceRepo
from app.config import Settings
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.voice import name_key, nick_point_id

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class NickService:
    """UC-9 + UC-10: the speaker menu and nick/"Me" assignment."""

    def __init__(
        self,
        repo: VoiceRepo,
        index: VoiceIndex,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._index = index
        self._settings = settings

    async def suggestions(
        self,
        owner_id: str,
        recording_id: str,
        speaker_id: str,
    ) -> dict[str, Any]:
        """UC-9: suggestions for the speaker menu; the Qdrant query happens only here (ADR-007)."""
        speaker = await self._repo.get_speaker(recording_id, speaker_id, owner_id)
        if speaker is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Speaker not found",
                recording_id=recording_id,
                speaker_id=speaker_id,
            )

        if speaker.get("is_me"):
            # Your own voice gets no nick (api.md): empty list, current = me.
            return {
                "speaker": {
                    "id": speaker["_id"],
                    "label": speaker.get("label"),
                    "current": {"kind": "me"},
                },
                "items": [],
            }

        current = self._current(speaker)
        centroid = speaker.get("centroid")
        if centroid is None:
            # Without a centroid a search is impossible; we do not fake a zero vector.
            return {
                "speaker": {
                    "id": speaker["_id"],
                    "label": speaker.get("label"),
                    "current": current,
                },
                "items": [],
            }

        items: list[dict[str, Any]] = []
        try:
            # "Me" first if the voice exists (kind=me point), then the nearest nicks (ADR-007).
            # We search for nothing beyond ownership: other people's points never enter the list.
            if await self._index.has_me(owner_id):
                items.append(_me_item())
            results = await self._index.search(
                owner_id,
                [float(v) for v in centroid],
                limit=self._settings.suggestion_limit,
            )
        except VoiceIndexUnavailable as exc:
            raise AppError(
                ErrorCode.VOICE_INDEX_UNAVAILABLE,
                "Voice index unavailable",
                recording_id=recording_id,
                speaker_id=speaker_id,
            ) from exc

        for point in results:
            payload = getattr(point, "payload", {})
            if payload.get("kind") == "me":
                continue  # already added first
            items.append(
                {
                    "kind": "nick",
                    "nick_id": payload.get("nick_id"),
                    "name": payload.get("name"),
                    "score": point.score,
                }
            )

        return {
            "speaker": {
                "id": speaker["_id"],
                "label": speaker.get("label"),
                "current": current,
            },
            "items": items,
        }

    async def assign(
        self,
        owner_id: str,
        recording_id: str,
        speaker_id: str,
        *,
        nick_id: str | None = None,
        name: str | None = None,
        me: bool = False,
    ) -> dict[str, Any]:
        """UC-10: assign an existing nick / create a new one / assign "Me".

        Three body forms, one semantic of "assign this speaker" (api.md). Returns the
        response object: `{speaker, nick, phrases_updated}`.
        """
        speaker = await self._repo.get_speaker(recording_id, speaker_id, owner_id)
        if speaker is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Speaker not found",
                recording_id=recording_id,
                speaker_id=speaker_id,
            )

        # Parsing the body form (exactly one of the three).
        if me:
            return await self._assign_me(speaker, owner_id, recording_id)
        if nick_id is not None:
            return await self._assign_existing(
                speaker, owner_id, recording_id, nick_id
            )
        if name is not None:
            return await self._assign_new(speaker, owner_id, recording_id, name)
        raise AppError(
            ErrorCode.NOT_FOUND,
            "Invalid assignment",
            recording_id=recording_id,
            speaker_id=speaker_id,
        )

    async def _assign_existing(
        self,
        speaker: dict[str, Any],
        owner_id: str,
        recording_id: str,
        nick_id: str,
    ) -> dict[str, Any]:
        nick = await self._repo.get_nick_by_id(nick_id, owner_id)
        if nick is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Nick not found",
                recording_id=recording_id,
                speaker_id=speaker["_id"],
            )

        current_nick_id = speaker.get("nick_id")
        if current_nick_id is not None and current_nick_id != nick_id:
            raise self._assignment_locked(recording_id, speaker["_id"])

        await self._repo.assign_speaker(
            recording_id,
            speaker["_id"],
            owner_id,
            label=nick["name"],
            nick_id=nick_id,
            is_me=False,
        )
        phrases_updated = await self._repo.set_phrases_side(
            recording_id, speaker["_id"], owner_id, side="left"
        )

        return {
            "speaker": self._speaker_response(
                speaker, label=nick["name"], nick_id=nick_id, is_me=False
            ),
            "nick": {"id": nick_id, "name": nick["name"], "reused": False},
            "phrases_updated": phrases_updated,
        }

    async def _assign_new(
        self,
        speaker: dict[str, Any],
        owner_id: str,
        recording_id: str,
        name: str,
    ) -> dict[str, Any]:
        current_nick_id = speaker.get("nick_id")
        if current_nick_id is not None:
            # Already assigned: a new name is a different nick for the same speaker → locked.
            # (If the name equals the current one — also 409, since it is "a different nick".)
            raise self._assignment_locked(recording_id, speaker["_id"])

        key = name_key(name)
        existing = await self._repo.find_nick_by_name_key(owner_id, key)

        if existing is not None:
            # Repeated name → reuse the existing nick, do not write a new point.
            nick_id = existing["_id"]
            await self._repo.assign_speaker(
                recording_id,
                speaker["_id"],
                owner_id,
                label=existing["name"],
                nick_id=nick_id,
                is_me=False,
            )
            phrases_updated = await self._repo.set_phrases_side(
                recording_id, speaker["_id"], owner_id, side="left"
            )
            return {
                "speaker": self._speaker_response(
                    speaker,
                    label=existing["name"],
                    nick_id=nick_id,
                    is_me=False,
                ),
                "nick": {"id": nick_id, "name": existing["name"], "reused": True},
                "phrases_updated": phrases_updated,
            }

        # New nick: a nicks document + a Qdrant point from the speaker centroid (immutable).
        nick_id = str(uuid.uuid4())
        now = _iso_now()
        nick_doc = {
            "_id": nick_id,
            "owner_user_id": owner_id,
            "name": name.strip(),
            "name_key": key,
            "created_from": {"recording_id": recording_id, "speaker_id": speaker["_id"]},
            "created_at": now,
        }
        try:
            nick = await self._repo.create_nick(nick_doc)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                ErrorCode.STORAGE_UNAVAILABLE, "Storage unavailable"
            ) from exc

        # The Qdrant point is best-effort (ADR-008). If unavailable, the nick is still created.
        centroid = speaker.get("centroid")
        if centroid is not None:
            try:
                await self._index.upsert_nick(
                    owner_id,
                    point_id=nick_point_id(owner_id, nick_id),
                    vector=[float(v) for v in centroid],
                    payload={
                        "owner_user_id": owner_id,
                        "kind": "nick",
                        "nick_id": nick_id,
                        "name": nick["name"],
                        "recording_id": recording_id,
                        "created_at": now,
                    },
                )
            except VoiceIndexUnavailable as exc:
                logger.warning(
                    "voice_index_write_failed nick_id=%s error=%s",
                    nick_id[:8],
                    type(exc).__name__,
                )
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "voice_index_write_failed nick_id=%s error=%s",
                    nick_id[:8],
                    type(exc).__name__,
                )

        await self._repo.assign_speaker(
            recording_id,
            speaker["_id"],
            owner_id,
            label=nick["name"],
            nick_id=nick_id,
            is_me=False,
        )
        phrases_updated = await self._repo.set_phrases_side(
            recording_id, speaker["_id"], owner_id, side="left"
        )

        return {
            "speaker": self._speaker_response(
                speaker, label=nick["name"], nick_id=nick_id, is_me=False
            ),
            "nick": {"id": nick_id, "name": nick["name"], "reused": False},
            "phrases_updated": phrases_updated,
        }

    async def _assign_me(
        self,
        speaker: dict[str, Any],
        owner_id: str,
        recording_id: str,
    ) -> dict[str, Any]:
        if speaker.get("nick_id") is not None:
            # Assigned to a nick → an attempt to make "Me" out of it is another nick → locked.
            raise self._assignment_locked(recording_id, speaker["_id"])

        await self._repo.assign_speaker(
            recording_id,
            speaker["_id"],
            owner_id,
            label="Me",
            nick_id=None,
            is_me=True,
        )
        phrases_updated = await self._repo.set_phrases_side(
            recording_id, speaker["_id"], owner_id, side="right"
        )

        return {
            "speaker": self._speaker_response(
                speaker, label="Me", nick_id=None, is_me=True
            ),
            "nick": {"id": None, "name": "Me", "reused": False},
            "phrases_updated": phrases_updated,
        }

    @staticmethod
    def _assignment_locked(recording_id: str, speaker_id: str) -> AppError:
        return AppError(
            ErrorCode.ASSIGNMENT_LOCKED,
            "Speaker is already assigned: splitting is not supported",
            recording_id=recording_id,
            speaker_id=speaker_id,
        )

    @staticmethod
    def _current(speaker: dict[str, Any]) -> dict[str, Any]:
        if speaker.get("is_me"):
            return {"kind": "me"}
        if speaker.get("nick_id"):
            return {"kind": "nick", "nick_id": speaker["nick_id"]}
        return {"kind": "none"}

    @staticmethod
    def _speaker_response(
        speaker: dict[str, Any],
        *,
        label: str,
        nick_id: str | None,
        is_me: bool,
    ) -> dict[str, Any]:
        return {
            "id": speaker["_id"],
            "label": label,
            "nick_id": nick_id,
            "is_me": is_me,
        }


def _me_item() -> dict[str, Any]:
    """The "Me" item in the suggestion list (first, without a score from Qdrant)."""
    return {"kind": "me", "name": "Me", "score": None}
