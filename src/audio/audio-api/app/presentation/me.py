"""The `/api/me` router: who I am and replacement of the "Me" voice (US-07).

`GET /api/me` — the owner's identity and whether a default voice exists.
`PUT /api/me/voice` — replace the voice from a note or a recording speaker (ADR-008).
The owner comes only from `X-Auth-Subject` (ADR-001); the body does not carry it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.me_service import MeService
from app.presentation.container import Container
from app.presentation.dependencies import get_current_owner
from app.presentation.schemas import MeVoiceUpdate

router = APIRouter(prefix="/api/me", tags=["me"])


def _me_service() -> MeService:
    return Container.instance().me_service


@router.get("")
async def get_me(
    me_service: Annotated[MeService, Depends(_me_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """`{label: "Me", has_default_voice, default_voice}` (api.md §GET /api/me)."""
    return await me_service.me(owner_id)


@router.put("/voice")
async def set_me_voice(
    body: MeVoiceUpdate,
    me_service: Annotated[MeService, Depends(_me_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """Replace the "Me" voice: one upsert by the deterministic id (ADR-008).

    `speaker_id: null` — voice from the note; otherwise — a recording speaker. Past chats are
    not relabelled.
    """
    return await me_service.set_voice(
        owner_id,
        recording_id=body.recording_id,
        speaker_id=body.speaker_id,
    )
