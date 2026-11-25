"""US-07 scenario: the default "Me" voice (UC-11).

Invariants (ADR-007/008/011, data-model.md, audio-api/api.md §GET /api/me, §PUT /api/me/voice):

- `Me` is one per owner. The Qdrant point is a replacement, not a creation: one `upsert` by the
  deterministic id `uuid5(owner, "me")` (`me_point_id`). A repeat call does not spawn
  a second point — the id is the same; a separate `delete` is not needed (and used to be broken).
- The voice vector is the same as for nicknames: the recording speaker's centroid or the note's
  `recordings.voice_embedding` (ADR-007, one space). The vector is not recomputed here.
- No vector (`voice_embedding` still `null`, note `too_short`) → `409 VOICE_NOT_READY`;
  dimension ≠ collection → `503 VOICE_INDEX_INCOMPATIBLE`, and **before** the point is written:
  the old point is preserved, Mongo is untouched.
- A foreign `recording_id`/`speaker_id` → `404 NOT_FOUND`: no other answer for foreign data.
- Past chats are not relabelled: `speakers.label` and `phrases.side` are neither read nor
  written here at all (ADR-008, item 4).
- The pointer is `owner_voices` (one document per owner); `recordings.is_default_voice`
  is set on exactly one note (cleared from all others via `clear_default_voice`).
  The writer of both is `audio-api` (ADR-011, ownership map).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.application.ports.recording_repo import RecordingRepo
from app.application.ports.voice_index import (
    VoiceIndex,
    VoiceIndexIncompatible,
    VoiceIndexUnavailable,
)
from app.application.ports.voice_repo import VoiceRepo
from app.config import Settings
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.voice import EMBEDDING_READY, ME_LABEL, me_point_id

logger = logging.getLogger(__name__)

# Why there is no vector: the value goes into the error `message`, the code is per contract.
_REASON_TEXT = {
    "no_embedding": "Voice is still being processed",
    "speaker_without_centroid": "The speaker has no voice vector",
}


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(vector: list[float]) -> list[float]:
    """Cosine in Qdrant requires normalized vectors (collection.md).

    Vectors of one model (centroid and note embedding) already arrive normalized;
    re-normalization is idempotent, and for a non-normalized one it protects the score.
    """
    norm = sum(float(v) * float(v) for v in vector) ** 0.5
    if norm <= 0:
        return [float(v) for v in vector]
    return [float(v) / norm for v in vector]


class MeService:
    """Owner representation and replacement of the "Me" voice."""

    def __init__(
        self,
        repo: RecordingRepo,
        voice_repo: VoiceRepo,
        index: VoiceIndex,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._voice_repo = voice_repo
        self._index = index
        self._settings = settings

    # -- GET /api/me ---------------------------------------------------------

    async def me(self, owner_id: str) -> dict[str, Any]:
        """Who I am and whether there is a default voice (api.md §GET /api/me).

        `default_voice` is `null` if there is no point. The source of truth is the `owner_voices`
        document **and** an existing point (ADR-008, item 5): no document, no voice;
        Qdrant
        unavailable → `503 VOICE_INDEX_UNAVAILABLE`, not a silent "no voice".
        """
        pointer = await self._voice_repo.get_owner_voice(owner_id)
        if pointer is None:
            return self._me_response(None)
        try:
            has_point = await self._index.has_me(owner_id)
        except VoiceIndexUnavailable as exc:
            raise self._index_unavailable() from exc
        if not has_point:
            # Orphaned pointer: suggestions do not see it (ADR-008 follow-ups).
            logger.warning("owner_voices_orphaned owner=%s", owner_id[:8])
            return self._me_response(None)
        doc = await self._repo.get_recording(pointer["recording_id"], owner_id)
        if doc is None:
            return self._me_response(None)
        return self._me_response({"doc": doc, "speaker_id": pointer.get("speaker_id")})

    def _me_response(self, default: dict[str, Any] | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "label": ME_LABEL,
            "has_default_voice": default is not None,
            "default_voice": None,
            "suggestion_limit": self._settings.suggestion_limit,
        }
        if default is not None:
            doc = default["doc"]
            body["default_voice"] = {
                "recording_id": doc["_id"],
                "kind": doc.get("kind"),
                "title": doc.get("title"),
            }
        return body

    # -- PUT /api/me/voice ---------------------------------------------------

    async def set_voice(
        self,
        owner_id: str,
        *,
        recording_id: str,
        speaker_id: str | None,
    ) -> dict[str, Any]:
        """Replaces the "Me" voice (api.md §PUT /api/me/voice).

        `speaker_id: null` — voice from the note (`recordings.voice_embedding`);
        otherwise — the recording speaker's centroid. Check order: ownership (404) → vector
        (409) → dimension (503) → Qdrant (one `upsert` by id) → Mongo pointers.
        So Qdrant and Mongo change only after all checks, and the old point lives until the
        new one is upserted successfully.
        """
        doc = await self._repo.get_recording(recording_id, owner_id)
        if doc is None:
            raise self._not_found(recording_id)

        if speaker_id is None:
            vector = doc.get("voice_embedding")
            if not vector or doc.get("processing", {}).get("embedding") != EMBEDDING_READY:
                # No vector: the note is finalizing, `too_short`, or the embedding failed.
                raise self._voice_not_ready(recording_id, "no_embedding")
            speaker_id = None
        else:
            speaker = await self._voice_repo.get_speaker(recording_id, speaker_id, owner_id)
            if speaker is None:
                raise self._not_found(recording_id, speaker_id=speaker_id)
            vector = speaker.get("centroid")
            if not vector:
                raise self._voice_not_ready(recording_id, "speaker_without_centroid")
            speaker_id = speaker["_id"]

        expected = self._settings.voice_embedding_size
        if len(vector) != expected:
            # Before writing the point: a mismatch is an index configuration error, the old point
            # stays (collection.md: we do not "fix" it silently).
            logger.warning(
                "voice_index_incompatible recording=%s dim=%d expected=%d",
                recording_id,
                len(vector),
                expected,
            )
            raise self._incompatible(len(vector), expected)

        try:
            point_id = me_point_id(owner_id)
        except ValueError as exc:  # a non-UUID owner is a routing error, not a 500
            raise AppError(
                ErrorCode.IDENTITY_MISSING, "X-Auth-Subject is not a UUID"
            ) from exc
        payload = {
            "owner_user_id": owner_id,
            "kind": "me",
            "recording_id": recording_id,
            "created_at": _iso_now(),
        }
        try:
            # Replacing the "Me" voice is one upsert by the deterministic id `uuid5(owner,"me")`
            # (ADR-008, item 1): the id is unique per owner by construction, so delete is not
            # needed and the replace is atomic — no "old deleted, new not written" window
            # (ADR-011, item 2). The previous implementation did a delete filtered on a nonexistent
            # field (never matched) — on the live Qdrant the point was not deleted at all.
            await self._index.upsert_me(
                owner_id,
                point_id=point_id,
                vector=_normalize(list(vector)),
                payload=payload,
            )
        except VoiceIndexIncompatible as exc:
            raise self._incompatible(len(vector), expected) from exc
        except VoiceIndexUnavailable as exc:
            raise self._index_unavailable() from exc

        # Mongo — after Qdrant: if the write failed, the pointer does not "lie" about the new voice
        # (the truth of "is there a voice" is the document AND the point, ADR-008).
        await self._voice_repo.set_owner_voice(
            owner_id,
            recording_id=recording_id,
            speaker_id=speaker_id,
            qdrant_point_id=point_id,
        )
        if doc.get("kind") == "voice_note":
            await self._repo.clear_default_voice(owner_id, keep_id=recording_id)
            await self._repo.set_default_voice(recording_id, owner_id, is_default=True)
        else:
            # Voice from an upload's speaker: no note of its own — clear the flag from the old one.
            await self._repo.clear_default_voice(owner_id, keep_id=None)

        logger.info(
            "me_voice_set owner=%s recording=%s source=%s",
            owner_id[:8],
            recording_id,
            "speaker" if speaker_id else "voice_note",
        )
        # The response has the same shape as `GET /api/me` (api.md): the client updates the
        # list and menu state without a second request.
        pointer = await self._voice_repo.get_owner_voice(owner_id)
        if pointer is None:
            return self._me_response(None)
        return self._me_response({"doc": doc, "speaker_id": pointer.get("speaker_id")})

    # -- errors --------------------------------------------------------------

    @staticmethod
    def _not_found(recording_id: str, *, speaker_id: str | None = None) -> AppError:
        extra: dict[str, Any] = {}
        if speaker_id is not None:
            extra["speaker_id"] = speaker_id
        return AppError(
            ErrorCode.NOT_FOUND,
            "Recording not found",
            recording_id=recording_id,
            **extra,
        )

    @staticmethod
    def _voice_not_ready(recording_id: str, reason: str) -> AppError:
        return AppError(
            ErrorCode.VOICE_NOT_READY,
            _REASON_TEXT[reason],
            recording_id=recording_id,
            reason=reason,
        )

    @staticmethod
    def _incompatible(dim: int, expected: int) -> AppError:
        return AppError(
            ErrorCode.VOICE_INDEX_INCOMPATIBLE,
            "Voice dimension does not match the index",
            dim=dim,
            expected=expected,
        )

    @staticmethod
    def _index_unavailable() -> AppError:
        return AppError(ErrorCode.VOICE_INDEX_UNAVAILABLE, "Voice index unavailable")
