"""Tests for the `audio.events` consumer: rank-based status transitions, terminal failed."""
from __future__ import annotations

import datetime

import pytest

from app.domain.recording import Recording
from app.domain.status import RecordingStatus
from tests.conftest import OTHER_OWNER, OWNER, RECORDING
from tests.fakes import FakeRecordingRepo


def _iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _seed(repo: FakeRecordingRepo, status: RecordingStatus = RecordingStatus.UPLOADED):
    rec = Recording(
        recording_id=RECORDING,
        owner_user_id=OWNER,
        title="Lecture",
        status=status,
        created_at=_iso(),
        updated_at=_iso(),
    )
    rec.processing = rec.default_processing()
    await repo.insert_recording(rec)


@pytest.fixture
def applier(container):
    return container.events_applier


async def test_diarization_started_advances_to_diarizing(applier, repo):
    await _seed(repo, RecordingStatus.UPLOADED)
    await applier.apply("diarization.started", RECORDING, OWNER, {})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "diarizing"


async def test_diarization_completed_advances_to_transcribing(applier, repo):
    await _seed(repo, RecordingStatus.DIARIZING)
    await applier.apply("diarization.completed", RECORDING, OWNER, {})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "transcribing"


async def test_late_diarization_started_does_not_rollback(applier, repo):
    await _seed(repo, RecordingStatus.TRANSCRIBING)
    await applier.apply("diarization.started", RECORDING, OWNER, {})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "transcribing"


async def test_transcription_completed_to_ready(applier, repo):
    await _seed(repo, RecordingStatus.TRANSCRIBING)
    await applier.apply("transcription.completed", RECORDING, OWNER, {"language": "ru"})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "ready"
    assert doc["language"] == "ru"
    assert doc["ready_at"] is not None


async def test_transcription_completed_writes_language_and_ready_at(applier, repo):
    # queue-audio-events contract: transcription.completed -> status ready + language + ready_at
    await _seed(repo, RecordingStatus.TRANSCRIBING)
    await applier.apply("transcription.completed", RECORDING, OWNER, {"language": "en"})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["language"] == "en"
    assert isinstance(doc["ready_at"], str) and doc["ready_at"].endswith("Z")


async def test_embedding_completed_sets_ready(applier, repo):
    await _seed(repo, RecordingStatus.READY)
    await applier.apply("embedding.completed", RECORDING, OWNER, {"dim_mismatch": False})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["processing"]["embedding"] == "ready"
    assert doc["status"] == "ready"  # the status does not change


async def test_embedding_completed_dim_mismatch_sets_incompatible(applier, repo):
    await _seed(repo, RecordingStatus.READY)
    await applier.apply("embedding.completed", RECORDING, OWNER, {"dim_mismatch": True})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["processing"]["embedding"] == "incompatible"


async def test_embedding_failed_sets_failed(applier, repo):
    await _seed(repo, RecordingStatus.READY)
    await applier.apply("embedding.failed", RECORDING, OWNER, {"error_code": "too_short"})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["processing"]["embedding"] == "failed"
    assert doc["status"] == "ready"  # orthogonal to status


async def test_embedding_foreign_owner_not_applied(applier, repo):
    await _seed(repo, RecordingStatus.READY)
    result = await applier.apply("embedding.completed", RECORDING, OTHER_OWNER, {})
    assert result is False
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["processing"]["embedding"] == "none"


async def test_failed_is_terminal(applier, repo):
    await _seed(repo, RecordingStatus.DIARIZING)
    await applier.apply("diarization.failed", RECORDING, OWNER, {"error_code": "failed_media"})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "failed"
    assert doc["processing"]["error_code"] == "failed_media"


async def test_ready_not_rolled_back_to_failed(applier, repo):
    await _seed(repo, RecordingStatus.READY)
    await applier.apply("diarization.failed", RECORDING, OWNER, {"error_code": "failed_media"})
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "ready"


async def test_foreign_event_ignored(applier, repo):
    await _seed(repo, RecordingStatus.UPLOADED)
    result = await applier.apply("diarization.started", RECORDING, OTHER_OWNER, {})
    assert result is False
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "uploaded"


async def test_unknown_event_ignored_without_error(applier, repo):
    await _seed(repo, RecordingStatus.UPLOADED)
    result = await applier.apply("some.unknown.event", RECORDING, OWNER, {})
    assert result is True
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "uploaded"


async def test_stall_watchdog_marks_failed(container, repo):
    await _seed(repo, RecordingStatus.DIARIZING)
    repo.stall_candidates.add(RECORDING)
    watchdog = container.stall_watchdog
    n = await watchdog.sweep()
    assert n == 1
    doc = repo.get_recording_sync(RECORDING, OWNER)
    assert doc["status"] == "failed"
    assert doc["processing"]["error_code"] == "stalled"
