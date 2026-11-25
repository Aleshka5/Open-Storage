"""`audio.embedding` message — the body per queue-audio-embedding/message.md."""

from __future__ import annotations

JOB = "e2f4a6b8-7c90-4d12-9a34-5b6c7d8e9f01"


def note_key(owner: str, recording: str) -> str:
    """Note object key: `u/{owner}/rec/{recording}/note.webm`."""
    return f"u/{owner}/rec/{recording}/note.webm"


def make_embedding_message(
    *,
    owner: str,
    recording: str,
    job: str = JOB,
    **overrides,
) -> dict:
    msg = {
        "schema_version": 1,
        "job_id": job,
        "recording_id": recording,
        "owner_user_id": owner,
        "audio_key": note_key(owner, recording),
        "target": "voice_note",
        "attempt": 0,
        "created_at": "2026-11-01T10:02:11Z",
    }
    msg.update(overrides)
    return msg
