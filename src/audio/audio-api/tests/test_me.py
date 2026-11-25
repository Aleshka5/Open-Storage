"""US-07 tests: the default "Me" voice (UC-11).

Each criterion of us-07/init.md is a separate test:

- `PUT /api/me/voice` from a note → `has_default_voice: true`, one point in Qdrant
  `kind: me` with id `uuid5(owner, "me")`; a repeat does not create a second one;
- switching the voice to a recording speaker replaces the same point (same id), `owner_voices`
  points at the speaker, `is_default_voice` is cleared from the old note;
- a foreign `recording_id`/`speaker_id` → `404`, a foreign point is neither read nor written;
- no vector (`voice_embedding` null / `too_short`) → `409 VOICE_NOT_READY`;
- dimension ≠ collection → `503 VOICE_INDEX_INCOMPATIBLE`, nothing written, the old point lives;
- `Me` first in suggestions;
- past chats do not change: `GET …/phrases` is identical before and after the voice change;
- note finalization: `audio.embedding` published, `embedding: pending`;
  a note shorter than 1 s — the job is not published, `embedding: failed`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.me_service import MeService
from app.application.voice_note_service import VoiceNoteService
from app.domain.app_error import AppError
from app.domain.errors import ErrorCode
from app.domain.voice import me_point_id
from app.presentation.api import create_app
from app.presentation.container import Container
from tests.conftest import OTHER_OWNER, OWNER, RECORDING
from tests.fakes import FakeAsrFactory, FakeMuxerFactory

NOTE = "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d"
UPLOAD = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"
SPEAKER = "a1b2c3d4-0000-4000-8000-000000000042"
SELF_SPEAKER = "a1b2c3d4-0000-4000-8000-0000000000ff"
EMB = [0.05] * 256

H = {"X-Auth-Subject": OWNER}

# -- helpers ----------------------------------------------------------------

def _client(settings, repo, voice_repo, voice_index, store, queue) -> TestClient:
    c = Container(
        settings,
        repo=repo,
        store=store,
        queue=queue,
        voice_repo=voice_repo,
        voice_index=voice_index,
    )
    Container.set_instance(c)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def _seed_note(repo, voice_repo, *, note_id=NOTE, owner=OWNER, title="Note 1", emb=EMB,
               embedding_state="ready", default=False):
    repo._recordings[note_id] = {
        "_id": note_id,
        "owner_user_id": owner,
        "title": title,
        "kind": "voice_note",
        "status": "ready",
        "audio_key": f"u/{owner}/rec/{note_id}/note.webm",
        "audio_content_type": "audio/webm",
        "audio_bytes": 1000,
        "duration_ms": 4200,
        "language": "ru",
        "is_default_voice": default,
        "voice_embedding": emb,
        "voice_embedding_model": "pyannote/embedding@rev" if emb else None,
        "processing": {"embedding": embedding_state, "phrases_done": 1, "phrases_total": 1},
        "created_at": "2026-11-01T10:00:00Z",
    }
    voice_repo.speakers[SELF_SPEAKER] = {
        "_id": SELF_SPEAKER,
        "owner_user_id": owner,
        "recording_id": note_id,
        "speaker_key": "SELF",
        "order_index": 1,
        "centroid": None,
        "label": "Me",
        "nick_id": None,
        "is_me": True,
    }
    voice_repo.phrases["phr-1"] = {
        "_id": "phr-1",
        "owner_user_id": owner,
        "recording_id": note_id,
        "speaker_id": SELF_SPEAKER,
        "seq": 1,
        "start_ms": 0,
        "end_ms": 4200,
        "text": "note text",
        "side": "right",
        "state": "final",
        "overlap": False,
        "revision": 3,
    }
    return note_id


def _seed_upload(repo, voice_repo, *, recording_id=UPLOAD, owner=OWNER):
    repo._recordings[recording_id] = {
        "_id": recording_id,
        "owner_user_id": owner,
        "title": "Lecture 4",
        "kind": "upload",
        "status": "ready",
        "audio_key": f"u/{owner}/rec/{recording_id}/original.m4a",
        "processed": "keep-me",  # an audio-api/other field — diarizer does not touch it
        "is_default_voice": False,
        "voice_embedding": None,
        "voice_embedding_model": None,
        "processing": {"embedding": "none"},
        "created_at": "2026-11-01T09:00:00Z",
    }
    voice_repo.speakers[SPEAKER] = {
        "_id": SPEAKER,
        "owner_user_id": owner,
        "recording_id": recording_id,
        "speaker_key": "SPEAKER_00",
        "order_index": 1,
        "centroid": [0.03] * 256,
        "label": "Speaker 1",
        "nick_id": None,
        "is_me": False,
    }
    n = 0
    for speaker_id, side in ((SPEAKER, "left"), ("spk-other", "left")):
        n += 1
        voice_repo.phrases[f"p-{n}"] = {
            "_id": f"p-{n}",
            "owner_user_id": owner,
            "recording_id": recording_id,
            "speaker_id": speaker_id,
            "seq": n,
            "start_ms": n * 1000,
            "end_ms": n * 1000 + 900,
            "text": f"phrase {n}",
            "side": side,
            "state": "final",
            "overlap": False,
            "revision": 0,
        }
    return recording_id


def _me_points(voice_index, owner=OWNER) -> list[tuple[str, dict[str, Any]]]:
    return [
        (pid, p)
        for pid, p in voice_index.points.items()
        if p["payload"].get("owner_user_id") == owner and p["payload"].get("kind") == "me"
    ]


# -- GET /api/me ------------------------------------------------------------

def test_me_without_voice(settings, repo, voice_repo, voice_index, store, queue):
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.get("/api/me", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Me"
    assert body["has_default_voice"] is False
    assert body["default_voice"] is None
    assert body["suggestion_limit"] == 5


def test_me_requires_identity(settings, repo, voice_repo, voice_index, store, queue):
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["detail"]["error_code"] == "IDENTITY_MISSING"


def test_me_after_voice_set(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE, "speaker_id": None}, headers=H
    ).status_code == 200

    body = client.get("/api/me", headers=H).json()
    assert body["has_default_voice"] is True
    assert body["default_voice"] == {
        "recording_id": NOTE,
        "kind": "voice_note",
        "title": "Note 1",
    }


# -- PUT /api/me/voice: happy + idempotency ---------------------------------

def test_set_voice_from_note_creates_single_me_point(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)

    r = client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["has_default_voice"] is True

    points = _me_points(voice_index)
    assert len(points) == 1
    pid, point = points[0]
    assert pid == me_point_id(OWNER)
    assert pid == str(uuid.uuid5(uuid.UUID(OWNER), "me"))
    assert point["payload"]["recording_id"] == NOTE
    assert len(point["vector"]) == 256
    # The vector is normalized: cosine in Qdrant is on normalized vectors (collection.md).
    norm = sum(v * v for v in point["vector"]) ** 0.5
    assert abs(norm - 1.0) < 1e-6

    doc = repo._recordings[NOTE]
    assert doc["is_default_voice"] is True
    assert voice_repo.owner_voices[OWNER]["recording_id"] == NOTE
    assert voice_repo.owner_voices[OWNER]["speaker_id"] is None

    # A second press — the same point, not a second one.
    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE}, headers=H
    ).status_code == 200
    assert len(_me_points(voice_index)) == 1
    # Replacing the voice is an `upsert` by the deterministic id `uuid5(owner,"me")` (ADR-008):
    # the id is owner-safe, so `delete` is not needed and the replace is atomic (ADR-011). Two PUTs
    # sent exactly two upserts to Qdrant, and there is still ONE point.
    assert voice_index.upserted_points.count(me_point_id(OWNER)) == 2
    assert voice_index.deleted_points.count(me_point_id(OWNER)) == 0
    assert len(_me_points(voice_index)) == 1


def test_set_voice_from_speaker_replaces_same_point(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo, default=True)
    _seed_upload(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)

    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE, "speaker_id": None}, headers=H
    ).status_code == 200
    first_pid = me_point_id(OWNER)

    r = client.put(
        "/api/me/voice", json={"recording_id": UPLOAD, "speaker_id": SPEAKER}, headers=H
    )
    assert r.status_code == 200, r.text

    points = _me_points(voice_index)
    assert len(points) == 1
    pid, point = points[0]
    assert pid == first_pid  # the id is deterministic — unchanged when the voice is replaced
    assert point["payload"]["recording_id"] == UPLOAD
    assert voice_repo.owner_voices[OWNER]["speaker_id"] == SPEAKER
    assert voice_repo.owner_voices[OWNER]["recording_id"] == UPLOAD
    # The flag is cleared from the old note; an upload has no flag of its own.
    assert repo._recordings[NOTE]["is_default_voice"] is False
    assert repo._recordings[UPLOAD]["is_default_voice"] is False
    assert sum(1 for d in repo._recordings.values() if d.get("is_default_voice")) == 0


def test_switch_between_notes_keeps_single_true(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo, note_id=NOTE, title="Note 1", default=True)
    _seed_note(
        repo, voice_repo, note_id="note-2", title="Note 2", emb=[0.07] * 256
    )
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": "note-2"}, headers=H)
    assert r.status_code == 200
    flags = {
        rid: d.get("is_default_voice")
        for rid, d in repo._recordings.items()
        if d["kind"] == "voice_note"
    }
    assert flags == {NOTE: False, "note-2": True}


def test_me_point_isolation_between_owners(
    settings, repo, voice_repo, voice_index, store, queue
):
    # A foreign owner with a voice of their own: points do not get mixed up (one nick/Me per owner).
    _seed_note(repo, voice_repo)
    other = str(uuid.uuid4())
    voice_index.points[me_point_id(other)] = {
        "vector": [0.1] * 256,
        "payload": {"owner_user_id": other, "kind": "me", "recording_id": "x"},
    }
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert me_point_id(OWNER) != me_point_id(other)
    assert len(_me_points(voice_index, OWNER)) == 1
    assert len(_me_points(voice_index, other)) == 1


# -- 404 for foreign data ---------------------------------------------------

def test_foreign_recording_is_404(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo, owner=OTHER_OWNER)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "NOT_FOUND"
    # A foreign point is neither read nor overwritten.
    assert voice_index.points == {}
    assert voice_repo.owner_voices == {}


def test_nonexistent_recording_is_404(settings, repo, voice_repo, voice_index, store, queue):
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": str(uuid.uuid4())}, headers=H)
    assert r.status_code == 404


def test_foreign_speaker_is_404(settings, repo, voice_repo, voice_index, store, queue):
    _seed_upload(repo, voice_repo, owner=OTHER_OWNER)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put(
        "/api/me/voice", json={"recording_id": UPLOAD, "speaker_id": SPEAKER}, headers=H
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error_code"] == "NOT_FOUND"
    assert voice_index.points == {}


def test_speaker_from_another_recording_is_404(
    settings, repo, voice_repo, voice_index, store, queue
):
    # The speaker exists and is ours, but belongs to another recording (recording_id did not match).
    _seed_upload(repo, voice_repo)
    _seed_note(repo, voice_repo, note_id="note-2")
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put(
        "/api/me/voice", json={"recording_id": "note-2", "speaker_id": SPEAKER}, headers=H
    )
    assert r.status_code == 404
    assert voice_index.points == {}


# -- 409 VOICE_NOT_READY ----------------------------------------------------

def test_note_without_embedding_is_409(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo, emb=None, embedding_state="pending")
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error_code"] == "VOICE_NOT_READY"
    assert detail["recording_id"] == NOTE
    assert voice_index.points == {}


def test_too_short_note_is_409(settings, repo, voice_repo, voice_index, store, queue):
    # `embedding.failed (too_short)` — there will never be a vector; the item is inactive.
    _seed_note(repo, voice_repo, emb=None, embedding_state="failed")
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert r.status_code == 409
    assert r.json()["detail"]["error_code"] == "VOICE_NOT_READY"


def test_speaker_without_centroid_is_409(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_upload(repo, voice_repo)
    voice_repo.speakers[SPEAKER]["centroid"] = None
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put(
        "/api/me/voice", json={"recording_id": UPLOAD, "speaker_id": SPEAKER}, headers=H
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error_code"] == "VOICE_NOT_READY"


def test_409_keeps_previous_voice(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo, default=True)
    _seed_note(repo, voice_repo, note_id="note-2", emb=None, embedding_state="pending")
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    before = dict(voice_index.points[me_point_id(OWNER)])

    r = client.put("/api/me/voice", json={"recording_id": "note-2"}, headers=H)
    assert r.status_code == 409
    assert voice_index.points[me_point_id(OWNER)] == before
    assert voice_repo.owner_voices[OWNER]["recording_id"] == NOTE
    assert repo._recordings[NOTE]["is_default_voice"] is True


# -- 503 VOICE_INDEX_INCOMPATIBLE / UNAVAILABLE -----------------------------

def test_dimension_mismatch_is_503_and_keeps_old_point(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo)
    _seed_note(
        repo, voice_repo, note_id="note-2", emb=[0.1] * 192, embedding_state="ready"
    )
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE}, headers=H
    ).status_code == 200
    old_point = dict(voice_index.points[me_point_id(OWNER)])
    assert len(old_point["vector"]) == 256

    r = client.put("/api/me/voice", json={"recording_id": "note-2"}, headers=H)
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error_code"] == "VOICE_INDEX_INCOMPATIBLE"
    assert detail["dim"] == 192
    assert detail["expected"] == 256
    # The point is not written, the old one stays; the pointer did not move.
    assert voice_index.points[me_point_id(OWNER)] == old_point
    assert voice_index.deleted_points.count(me_point_id(OWNER)) == 0
    assert voice_index.upserted_points.count(me_point_id(OWNER)) == 1
    assert voice_repo.owner_voices[OWNER]["recording_id"] == NOTE


def test_index_unavailable_is_503(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    voice_index.available = False
    r = client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "VOICE_INDEX_UNAVAILABLE"
    assert voice_repo.owner_voices == {}


def test_me_reports_unavailable_index(settings, repo, voice_repo, voice_index, store, queue):
    _seed_note(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    voice_index.available = False
    r = client.get("/api/me", headers=H)
    assert r.status_code == 503
    assert r.json()["detail"]["error_code"] == "VOICE_INDEX_UNAVAILABLE"


# -- suggestions: Me first --------------------------------------------------

def test_me_is_first_suggestion_after_voice_set(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo)
    _seed_upload(repo, voice_repo)
    # The owner nick closest to the centroid — "Me" is still first (ADR-007).
    voice_index.points["nick-close"] = {
        "vector": [0.03] * 256,
        "payload": {
            "owner_user_id": OWNER,
            "kind": "nick",
            "nick_id": "n1",
            "name": "Anya",
            "recording_id": UPLOAD,
        },
    }
    client = _client(settings, repo, voice_repo, voice_index, store, queue)

    before = client.get(
        f"/api/recordings/{UPLOAD}/speakers/{SPEAKER}/suggestions", headers=H
    ).json()
    assert [i["kind"] for i in before["items"]] == ["nick"]

    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE}, headers=H
    ).status_code == 200

    after = client.get(
        f"/api/recordings/{UPLOAD}/speakers/{SPEAKER}/suggestions", headers=H
    ).json()
    kinds = [i["kind"] for i in after["items"]]
    assert kinds[0] == "me"
    assert set(kinds[1:]) == {"nick"}
    assert after["items"][0]["name"] == "Me"
    assert after["speaker"]["current"] == {"kind": "none"}  # no auto-assignment


def test_me_item_not_duplicated_when_search_returns_me(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo)
    _seed_upload(repo, voice_repo)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    client.put("/api/me/voice", json={"recording_id": NOTE}, headers=H)
    body = client.get(
        f"/api/recordings/{UPLOAD}/speakers/{SPEAKER}/suggestions", headers=H
    ).json()
    # The `kind=me` point is not duplicated in the search output: "Me" is added once, first.
    kinds = [i["kind"] for i in body["items"]]
    assert kinds.count("me") == 1
    assert kinds[0] == "me"


# -- past chats do not change (ADR-008) -------------------------------------

def test_old_labels_unchanged_before_and_after_voice_change(
    settings, repo, voice_repo, voice_index, store, queue
):
    _seed_note(repo, voice_repo, default=True)
    _seed_upload(repo, voice_repo)
    # In a past chat the speaker is already assigned "Me" — a voice change must not touch that.
    voice_repo.speakers["spk-other"] = {
        "_id": "spk-other",
        "owner_user_id": OWNER,
        "recording_id": UPLOAD,
        "speaker_key": "SPEAKER_01",
        "order_index": 2,
        "centroid": [0.02] * 256,
        "label": "Dima",
        "nick_id": "n-dima",
        "is_me": False,
    }
    voice_repo.phrases["p-2"]["side"] = "left"
    client = _client(settings, repo, voice_repo, voice_index, store, queue)

    def phrases() -> dict[str, Any]:
        return client.get(
            f"/api/recordings/{UPLOAD}/phrases?after_seq=0&limit=500", headers=H
        ).json()

    before = phrases()
    assert before["items"]

    # We change the voice by note, then by recording speaker.
    assert client.put(
        "/api/me/voice", json={"recording_id": NOTE}, headers=H
    ).status_code == 200
    assert phrases() == before

    assert client.put(
        "/api/me/voice", json={"recording_id": UPLOAD, "speaker_id": SPEAKER}, headers=H
    ).status_code == 200
    after = phrases()
    # Labels and sides are identical: past chats are not relabelled.
    assert after["items"] == before["items"]
    assert [(i["label"], i["side"]) for i in after["items"]] == [
        ("Speaker 1", "left"),
        ("Dima", "left"),
    ]
    # The voice-source speaker stays unassigned (PUT /api/me/voice does not assign a nick).
    assert voice_repo.speakers[SPEAKER]["label"] == "Speaker 1"
    assert voice_repo.speakers[SPEAKER]["is_me"] is False


# -- service directly: order of checks --------------------------------------

async def test_service_404_before_qdrant(settings, repo, voice_repo, voice_index):
    service = MeService(repo, voice_repo, voice_index, settings)
    with pytest.raises(AppError) as err:
        await service.set_voice(OWNER, recording_id=RECORDING, speaker_id=None)
    assert err.value.code is ErrorCode.NOT_FOUND
    assert voice_index.upserted_points == []


async def test_service_incompatible_before_delete(settings, repo, voice_repo, voice_index):
    # The vector exists (dim_mismatch) but the state is `incompatible`: "no ready voice" must not
    # mask a dimension error — 409 first, then 503.
    _seed_note(repo, voice_repo, emb=[0.1] * 128, embedding_state="ready")
    service = MeService(repo, voice_repo, voice_index, settings)
    with pytest.raises(AppError) as err:
        await service.set_voice(OWNER, recording_id=NOTE, speaker_id=None)
    assert err.value.code is ErrorCode.VOICE_INDEX_INCOMPATIBLE
    # Neither delete nor upsert: the mismatch is detected before the point is written.
    assert voice_index.deleted_points == []
    assert voice_index.upserted_points == []


# -- note finalization publishes audio.embedding ----------------------------

def _note_service(repo, voice_repo, store, queue, settings):
    async def _probe():
        return True, False

    svc = VoiceNoteService(
        repo, voice_repo, store, FakeAsrFactory(), settings, asr_probe=_probe, queue=queue
    )
    svc._muxer_factory = FakeMuxerFactory()  # noqa: SLF001 — no ffmpeg in tests
    return svc


async def _finalize(svc, repo, *, frames: int):
    created = await svc.create(OWNER)
    recording_id = created["recording_id"]
    svc._asr_factory.add(  # noqa: SLF001
        __import__("tests.fakes", fromlist=["FakeAsrStream"]).FakeAsrStream(
            server_frames=[{"type": "final", "text": "hello", "end_ms": frames * 100},
                           {"type": "done"}]
        )
    )
    inbox = [b"\x00\x00" * 1600] * frames + [{"type": "stop"}]
    closed: list[int] = []

    async def receive():
        return inbox.pop(0) if inbox else None

    async def send(_msg):
        return None

    async def close(code):
        closed.append(code)

    await svc.run_stream(OWNER, recording_id, receive=receive, send_text=send, close=close)
    return recording_id


def _embedding_jobs(queue) -> list[dict[str, Any]]:
    return [b for q, b, _ in queue.published if q == "audio.embedding"]


async def test_finalize_publishes_audio_embedding(settings, repo, voice_repo, store, queue):
    svc = _note_service(repo, voice_repo, store, queue, settings)
    recording_id = await _finalize(svc, repo, frames=20)  # 2 s
    jobs = _embedding_jobs(queue)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["schema_version"] == 1
    assert job["recording_id"] == recording_id
    assert job["owner_user_id"] == OWNER
    assert job["audio_key"] == f"u/{OWNER}/rec/{recording_id}/note.webm"
    assert job["target"] == "voice_note"
    assert job["attempt"] == 0
    assert job["job_id"] and job["created_at"]
    doc = repo.get_recording_sync(recording_id, OWNER)
    assert doc["processing"]["embedding"] == "pending"
    assert doc["status"] == "ready"


async def test_short_note_does_not_publish_embedding(
    settings, repo, voice_repo, store, queue
):
    svc = _note_service(repo, voice_repo, store, queue, settings)
    recording_id = await _finalize(svc, repo, frames=9)  # 0.9 s < 1 s
    assert _embedding_jobs(queue) == []
    doc = repo.get_recording_sync(recording_id, OWNER)
    # There will be no vector: the item is inactive, PUT answers 409 (see the tests above).
    assert doc["processing"]["embedding"] == "failed"
    assert doc["voice_embedding"] is None


async def test_embedding_publish_failure_keeps_note_ready(
    settings, repo, voice_repo, store, queue
):
    svc = _note_service(repo, voice_repo, store, queue, settings)
    queue.fail_publish = True
    recording_id = await _finalize(svc, repo, frames=20)
    doc = repo.get_recording_sync(recording_id, OWNER)
    assert doc["status"] == "ready"  # the note does not suffer from the broker refusal
    assert doc["processing"]["embedding"] == "failed"


async def test_short_note_set_voice_is_409_via_http(
    settings, repo, voice_repo, voice_index, store, queue
):
    # End-to-end scenario: a short note is finalized → PUT /api/me/voice = 409.
    svc = _note_service(repo, voice_repo, store, queue, settings)
    recording_id = await _finalize(svc, repo, frames=5)
    client = _client(settings, repo, voice_repo, voice_index, store, queue)
    r = client.put("/api/me/voice", json={"recording_id": recording_id}, headers=H)
    assert r.status_code == 409
    assert r.json()["detail"]["error_code"] == "VOICE_NOT_READY"
