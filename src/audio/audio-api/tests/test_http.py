"""Identity (X-Auth-Subject) and HTTP surface tests — happy + negative (api.md)."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app.presentation.api import create_app
from app.presentation.container import Container
from tests.conftest import OWNER, VALID_WAV


def _build_client(settings, repo, voice_repo, voice_index, store, queue):
    c = Container(
        settings,
        repo=repo,
        store=store,
        queue=queue,
        voice_repo=voice_repo,
        voice_index=voice_index,
    )
    Container.set_instance(c)
    app = create_app(settings)
    return TestClient(app, raise_server_exceptions=False)


def _ffprobe_wav() -> bytes:
    """Generates a real short WAV via ffmpeg if available, otherwise byte by byte."""
    import subprocess

    try:
        r = subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
             "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True, check=False, timeout=10,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return VALID_WAV


def test_identity_missing_returns_401(settings, repo, voice_repo, voice_index, store, queue):
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.get("/api/recordings")
    assert r.status_code == 401
    assert r.json()["detail"]["error_code"] == "IDENTITY_MISSING"


def test_identity_non_uuid_returns_401(settings, repo, voice_repo, voice_index, store, queue):
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.get("/api/recordings", headers={"X-Auth-Subject": "not-a-uuid"})
    assert r.status_code == 401
    assert r.json()["detail"]["error_code"] == "IDENTITY_MISSING"


def test_legacy_user_id_header_is_not_identity(
    settings, repo, voice_repo, voice_index, store, queue
):
    """A pre-v1 user id header, with no subject, is 401 IDENTITY_MISSING."""
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    removed = "X-Auth-" + "User-Id"
    r = client.get("/api/recordings", headers={removed: OWNER})
    assert r.status_code == 401
    assert r.json()["detail"]["error_code"] == "IDENTITY_MISSING"


def test_noncanonical_uuid_forms_are_401(
    settings, repo, voice_repo, voice_index, store, queue
):
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    for value in (OWNER.replace("-", ""), f"urn:uuid:{OWNER}", "{" + OWNER + "}"):
        r = client.get("/api/recordings", headers={"X-Auth-Subject": value})
        assert r.status_code == 401, value
        assert r.json()["detail"]["error_code"] == "IDENTITY_MISSING", value


def test_uppercase_subject_is_used_lowercase(
    settings, repo, voice_repo, voice_index, store, queue
):
    """Upper-case hex is accepted; the handler looks up the lower-case owner."""
    rid = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"
    repo._recordings[rid] = {
        "_id": rid,
        "owner_user_id": OWNER,
        "title": "Lecture",
        "kind": "upload",
        "status": "uploaded",
        "audio_key": f"u/{OWNER}/rec/{rid}/original.wav",
        "audio_content_type": "audio/wav",
        "audio_bytes": 4,
        "duration_ms": 1000,
        "created_at": "2026-11-01T09:00:00Z",
    }
    repo._by_owner[OWNER] = [rid]
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.get(
        f"/api/recordings/{rid}",
        headers={"X-Auth-Subject": OWNER.upper()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["recording"]["id"] == rid
    stored = repo.get_recording_sync(rid, OWNER)
    assert stored is not None
    assert stored["owner_user_id"] == OWNER.lower()
    assert stored["audio_key"] == f"u/{OWNER}/rec/{rid}/original.wav"
    assert repo.get_recording_sync(rid, OWNER.upper()) is None


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
def test_upload_happy_path(settings, repo, voice_repo, voice_index, store, queue):
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    payload = _ffprobe_wav()
    r = client.post(
        "/api/recordings",
        headers={"X-Auth-Subject": OWNER},
        files={"file": ("lecture.wav", payload, "audio/wav")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "uploaded"
    rid = body["id"]
    # The recordings document in `uploaded`, the key in MinIO.
    doc = repo.get_recording_sync(rid, OWNER)
    assert doc is not None
    assert doc["status"] == "uploaded"
    assert doc["owner_user_id"] == OWNER
    assert f"u/{OWNER}/rec/{rid}/original.wav" in store.objects
    # A message in audio.diarization.
    assert queue.published
    qname, msg, props = queue.published[0]
    assert qname == "audio.diarization"
    assert msg["schema_version"] == 1
    assert msg["recording_id"] == rid
    assert msg["owner_user_id"] == OWNER
    assert msg["audio_key"] == f"u/{OWNER}/rec/{rid}/original.wav"
    assert props["message_id"] == msg["job_id"]
    assert props["correlation_id"] == rid


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
def test_upload_non_audio_returns_415(settings, repo, voice_repo, voice_index, store, queue):
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.post(
        "/api/recordings",
        headers={"X-Auth-Subject": OWNER},
        files={"file": ("notes.txt", b"hello world not audio", "text/plain")},
    )
    assert r.status_code == 415
    assert r.json()["detail"]["error_code"] == "UNSUPPORTED_MEDIA"


def test_upload_too_large_returns_413(settings, repo, voice_repo, voice_index, store, queue):
    settings.max_upload_bytes = 100  # a tiny limit
    client = _build_client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.post(
        "/api/recordings",
        headers={"X-Auth-Subject": OWNER},
        files={"file": ("big.wav", VALID_WAV, "audio/wav")},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["error_code"] == "PAYLOAD_TOO_LARGE"
    # The object is not written.
    assert not store.objects
