"""Service-level upload tests: STORAGE_UNAVAILABLE, QUEUE_UNAVAILABLE."""
from __future__ import annotations

import shutil
import subprocess

import pytest

from app.application.recording_service import RecordingService
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from tests.conftest import OWNER


def _make_wav() -> bytes:
    try:
        r = subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
             "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True, check=False, timeout=10,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    from tests.conftest import VALID_WAV

    return VALID_WAV


def _chunks(data: bytes):
    async def _it():
        yield data

    return _it()


async def _upload(svc, data: bytes, filename: str = "x.wav"):
    return await svc.upload(OWNER, filename, _chunks(data), title=None)


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
async def test_storage_unavailable_returns_503(container):
    container.store.fail_put = True
    svc = RecordingService(container.repo, container.store, container.queue, container.settings)
    with pytest.raises(AppError) as exc:
        await _upload(svc, _make_wav())
    assert exc.value.code == ErrorCode.STORAGE_UNAVAILABLE


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
async def test_queue_unavailable_records_failed(container, repo):
    container.queue.fail_publish = True
    svc = RecordingService(container.repo, container.store, container.queue, container.settings)
    with pytest.raises(AppError) as exc:
        await _upload(svc, _make_wav())
    assert exc.value.code == ErrorCode.QUEUE_UNAVAILABLE
    rid = exc.value.recording_id
    assert rid is not None
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc is not None
    assert doc["status"] == "failed"
    assert doc["processing"]["error_code"] == "queue_unavailable"
    # the object is written (not deleted)
    assert f"u/{OWNER}/rec/{rid}/original.wav" in container.store.objects
