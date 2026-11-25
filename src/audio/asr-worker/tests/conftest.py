"""Shared asr-worker fixtures: settings, a handler with fakes, a synthetic WAV."""

from __future__ import annotations

import subprocess

import pytest

from app.application.transcribe_batch import TranscribeBatchHandler
from app.config import Settings
from tests.fakes import (
    FakeGpuLease,
    FakeObjectStore,
    FakePhraseRepo,
    FakeQueue,
    fake_model,
)

OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
OTHER_OWNER = "11111111-2222-3333-4444-555555555555"
RECORDING = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"
JOB = "5c1a9d77-2b3e-4a6f-8d10-4f1c9e2b7a33"


def norm_key(owner: str = OWNER, recording: str = RECORDING) -> str:
    return f"u/{owner}/rec/{recording}/norm.wav"


def make_turn(
    turn_id: str, speaker_key: str, start_ms: int, end_ms: int, overlap: bool = False
) -> dict:
    return {
        "turn_id": turn_id,
        "speaker_key": speaker_key,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "overlap": overlap,
    }


def make_message(turns: list[dict] | None = None, **overrides) -> dict:
    msg = {
        "schema_version": 1,
        "job_id": JOB,
        "recording_id": RECORDING,
        "owner_user_id": OWNER,
        "audio_key": norm_key(),
        "language_hint": None,
        "turns": turns if turns is not None else _default_turns(),
        "attempt": 0,
        "created_at": "2026-11-01T09:21:47Z",
    }
    msg.update(overrides)
    return msg


def _default_turns() -> list[dict]:
    # Three turns: SPEAKER_00 (0..3.52s), SPEAKER_01 (3.52..8.14s), SPEAKER_00 (8.14..12.96s).
    return [
        make_turn("t0001", "SPEAKER_00", 0, 3520, False),
        make_turn("t0002", "SPEAKER_01", 3520, 8140, True),
        make_turn("t0003", "SPEAKER_00", 8140, 12960, False),
    ]


def make_wav(freq: int = 440, duration: float = 0.3) -> bytes:
    """Synthetic WAV (16 kHz mono s16le) via ffmpeg; fallback — silence."""
    try:
        r = subprocess.run(
            [
                "ffmpeg",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                "-f", "wav", "pipe:1",
            ],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    from tests.conftest import VALID_WAV

    return VALID_WAV


# Minimal valid WAV: a 44-byte header plus a bit of silence (16 kHz mono s16le).
_WAV_HEADER = (
    b"RIFF"
    + (36 + 1600).to_bytes(4, "little")
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little")
    + (1).to_bytes(2, "little")
    + (16000).to_bytes(4, "little")
    + (32000).to_bytes(4, "little")
    + (2).to_bytes(2, "little")
    + (16).to_bytes(2, "little")
    + b"data"
    + (1600).to_bytes(4, "little")
)
VALID_WAV = _WAV_HEADER + b"\x00" * 1600


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(scratch_dir=str(tmp_path / "audio"))


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def repo() -> FakePhraseRepo:
    return FakePhraseRepo()


@pytest.fixture
def lease() -> FakeGpuLease:
    return FakeGpuLease()


@pytest.fixture
def model():
    return fake_model()


@pytest.fixture
def handler(settings, model, store, repo, queue, lease) -> TranscribeBatchHandler:
    return TranscribeBatchHandler(
        settings=settings,
        model=model,
        store=store,
        repo=repo,
        queue=queue,
        lease=lease,
    )
