"""Pydantic request body schemas (PATCH, POST)."""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class NickAssignment(BaseModel):
    """The three body forms of POST …/speakers/{sid}/nick (api.md). Exactly one is filled in."""

    nick_id: str | None = None
    name: str | None = Field(default=None, max_length=120)
    me: bool | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> NickAssignment:
        forms = [self.nick_id is not None, self.name is not None, self.me is True]
        if sum(forms) != 1:
            raise ValueError(
                "Specify exactly one of: nick_id, name or me=true"
            )
        if self.name is not None and not self.name.strip():
            raise ValueError("Nick name must not be empty")
        return self


class MeVoiceUpdate(BaseModel):
    """Body of `PUT /api/me/voice` (api.md): a note (`speaker_id: null`) or a speaker."""

    recording_id: str
    speaker_id: str | None = None
