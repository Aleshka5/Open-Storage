"""Shared test fixtures: fake ports and an assembled Container."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.presentation.container import Container
from tests.fakes import (
    FakeAudioStore,
    FakeQueue,
    FakeRecordingRepo,
    FakeVoiceIndex,
    FakeVoiceRepo,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        max_upload_bytes=1024 * 1024,  # 1 MiB for the limit test
        processing_stall_seconds=900,
        qdrant_url="http://qdrant:6333",
        asr_stream_url="ws://asr-worker:8020/v1/stream",
        # Empty production defaults must not make `"" in body` succeed.
        s3_access_key="test-s3-access",
        s3_secret_key="test-s3-secret",
        rabbitmq_url="amqp://audio-test:audio-test@rabbit:5672/",
    )


@pytest.fixture
def repo() -> FakeRecordingRepo:
    return FakeRecordingRepo()


@pytest.fixture
def voice_repo() -> FakeVoiceRepo:
    return FakeVoiceRepo()


@pytest.fixture
def voice_index() -> FakeVoiceIndex:
    return FakeVoiceIndex()


@pytest.fixture
def store() -> FakeAudioStore:
    return FakeAudioStore()


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def container(settings, repo, voice_repo, voice_index, store, queue) -> Container:
    c = Container(
        settings,
        repo=repo,
        store=store,
        queue=queue,
        voice_repo=voice_repo,
        voice_index=voice_index,
    )
    Container.set_instance(c)
    return c


# Test identifiers.
OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
OTHER_OWNER = "11111111-2222-3333-4444-555555555555"
RECORDING = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"

# Minimal valid WAV: a 44-byte header + a bit of silence.
_WAV_HEADER = (
    b"RIFF" + (36 + 1600).to_bytes(4, "little") + b"WAVE"
    b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
    + (1).to_bytes(2, "little") + (16000).to_bytes(4, "little")
    + (32000).to_bytes(4, "little") + (2).to_bytes(2, "little")
    + (16).to_bytes(2, "little") + b"data" + (1600).to_bytes(4, "little")
)
VALID_WAV = _WAV_HEADER + b"\x00" * 1600
