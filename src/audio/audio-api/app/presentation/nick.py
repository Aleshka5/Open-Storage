"""The `/api/recordings/{id}/speakers/{sid}` router: UC-9 (suggestions) and UC-10 (nick/"Me")."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.nick_service import NickService
from app.presentation.container import Container
from app.presentation.dependencies import get_current_owner
from app.presentation.schemas import NickAssignment

router = APIRouter(prefix="/api/recordings", tags=["speakers"])


def _nick_service() -> NickService:
    return Container.instance().nick_service


@router.get("/{recording_id}/speakers/{speaker_id}/suggestions")
async def speaker_suggestions(
    recording_id: str,
    speaker_id: str,
    nick_service: Annotated[NickService, Depends(_nick_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """Suggestions for the speaker menu. Called only when the menu opens (ADR-007)."""
    return await nick_service.suggestions(owner_id, recording_id, speaker_id)


@router.post("/{recording_id}/speakers/{speaker_id}/nick")
async def assign_speaker_nick(
    recording_id: str,
    speaker_id: str,
    body: NickAssignment,
    nick_service: Annotated[NickService, Depends(_nick_service)],
    owner_id: Annotated[str, Depends(get_current_owner)],
):
    """Assign an existing nick / create a new one / assign "Me" (three body forms)."""
    return await nick_service.assign(
        owner_id,
        recording_id,
        speaker_id,
        nick_id=body.nick_id,
        name=body.name,
        me=body.me is True,
    )
