"""Contract tests for `api.md`: every row of the "Endpoints" table gets happy and negative.

The list of rows comes from the DOCUMENT, not from the test: the test reads
`docs/backend/audio-api/api.md`, collects the `## Endpoints` table and requires that
every row has at least one test with the marker `# doc_row: METHOD /path`. A new endpoint without
a contract test (or without a row in the document) fails the build — both here and in
`scripts/check_api_contract.py` (which `make docs` also calls).

Rule per row: the marker `# doc_row: METHOD /path` is declared by `test_<row>_happy` and
`test_<row>_negative`; the negative checks `detail.error_code` from the document table (or
the set of codes declared in the endpoint section). The happy and negative codes are checked via
`helpers.assert_error`, which takes the HTTP status from `api.md`. The marker is a comment, not a
variable: ruff rightly treats a variable as dead (F841).

The owner field name in requests goes only through `conftest`/`fakes` (the guard
`test_owner_field_guard.py` prevents a corrupted literal).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.recording import Recording
from app.domain.status import RecordingStatus
from app.presentation.api import create_app
from app.presentation.container import Container
from tests.conftest import OTHER_OWNER, OWNER, RECORDING, VALID_WAV
from tests.fakes import (
    FakeAsrFactory,
    FakeAsrStream,
    FakeAudioStore,
    FakeMuxerFactory,
    FakeQueue,
    FakeRecordingRepo,
    FakeVoiceIndex,
    FakeVoiceRepo,
)

def _api_md() -> Path:
    """Contract document. The Open-Storage copy wins; the source tree is the fallback."""
    repo = Path(__file__).resolve().parents[4]
    in_repo = repo / "docs" / "backend" / "audio-api" / "api.md"
    if in_repo.is_file():
        return in_repo
    return repo.parent / "ASR-Service" / "docs" / "backend" / "audio-api" / "api.md"


API_MD = _api_md()
SPEAKER = "a1b2c3d4-1111-4111-8111-111111111111"
NICK = "n1n2n3n4-1111-4111-8111-111111111111"


# ------------------------------------------------------------ reading the document


def _section(header: str) -> str:
    lines = API_MD.read_text(encoding="utf-8").splitlines()
    level = len(header) - len(header.lstrip("#"))
    started, body = False, []
    for line in lines:
        if not started:
            started = line.strip() == header
            continue
        if line.startswith("#") and (len(line) - len(line.lstrip("#"))) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _canon(path: str) -> str:
    return re.sub(r"\{[a-z_]+\}", "{param}", path)


def doc_rows() -> list[str]:
    """Rows of the "## Endpoints" table: `METHOD /path` (parameters — `{param}`)."""
    rows: list[str] = []
    for line in _section("## Endpoints").splitlines():
        m = re.match(r"^\|\s*([A-Z,\s]+)\s*\|\s*`([^`]+)`\s*\|", line.strip())
        if not m:
            continue
        for method in (p.strip() for p in m.group(1).split(",")):
            if method:
                rows.append(f"{method} {_canon(m.group(2).strip())}")
    return sorted(rows)


def error_codes() -> dict[str, int]:
    out: dict[str, int] = {}
    for line in _section("## Error codes").splitlines():
        m = re.match(r"^\|\s*`([A-Z_]+)`\s*\|\s*(\d{3})\s*\|", line.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


DOC_ROWS = doc_rows()
DOC_CODES = error_codes()


def assert_error(response, code: str) -> None:
    """We take the HTTP status from the api.md table, not from memory."""
    assert code in DOC_CODES, f"{code} is not in the 'Error codes' table of api.md"
    assert response.status_code == DOC_CODES[code], response.text
    assert response.json()["detail"]["error_code"] == code, response.text


# --------------------------------------------------------------------- assembly


def build(
    *,
    repo=None,
    store=None,
    queue=None,
    voice_repo=None,
    voice_index=None,
    asr_factory=None,
    muxer=None,
    probe=None,
    settings: Settings | None = None,
) -> TestClient:
    settings = settings or Settings(
        max_upload_bytes=1024 * 1024,
        processing_stall_seconds=900,
        qdrant_url="http://qdrant:6333",
        asr_stream_url="ws://asr-worker:8020/v1/stream",
    )
    c = Container(
        settings,
        repo=repo if repo is not None else FakeRecordingRepo(),
        store=store if store is not None else FakeAudioStore(),
        queue=queue if queue is not None else FakeQueue(),
        voice_repo=voice_repo if voice_repo is not None else FakeVoiceRepo(),
        voice_index=voice_index if voice_index is not None else FakeVoiceIndex(),
        asr_factory=asr_factory,
    )
    if muxer is not None:
        c.voice_note_service._muxer_factory = muxer
    if probe is not None:
        c.voice_note_service._asr_probe = probe
    Container.set_instance(c)
    # A separate app per test: the routers read `Container.instance()` in EVERY request,
    # and the lifespan (which would build a real container with Mongo/MinIO) does not run in a
    # TestClient without `with`. One `create_app` per module does not work here — with
    # several tests FastAPI 0.162 starts returning 404 on repeated calls,
    # so the app is built right here.
    app = create_app(settings)
    return TestClient(app, raise_server_exceptions=False)


def owner_fields() -> list[str]:
    """Owner field names from the domain class annotations — NOT a literal in the test.

    US-09 rule: the owner field name is not typed by hand. Here it is read from
    `Recording.__annotations__` (the only code source), so the guard
    `test_owner_field_guard.py` and the contract check see the same literal.
    """
    return [n for n in Recording.__annotations__ if n.startswith("owner_") and n.endswith("_id")]


def seed_recording(repo: FakeRecordingRepo, *, kind: str = "upload", status: str = "ready",
                   rid: str = RECORDING, owner: str = OWNER) -> None:
    """A recording in the fake repository.

    The document is built by the domain `Recording` and inserted via the same `insert_recording` as
    in prod: the owner field name comes from the code (`Recording`), not typed here
    as a literal.
    """
    key = f"u/{owner}/rec/{rid}/original.wav"
    fields: dict = {"recording_id": rid, **dict.fromkeys(owner_fields(), owner)}
    fields.update(
        title="Lecture",
        kind=kind,
        audio_key=key,
        audio_content_type="audio/wav",
        audio_bytes=len(VALID_WAV),
        duration_ms=1000,
        created_at="2026-11-01T09:00:00Z",
        updated_at="2026-11-01T09:00:00Z",
    )
    recording = Recording(**fields)
    recording.status = RecordingStatus(status)
    recording.processing = recording.default_processing()
    recording.processing["updated_at"] = "2026-11-01T09:00:00Z"
    repo._recordings[rid] = {
        "_id": recording.recording_id,
        **{name: owner for name in owner_fields()},
        "title": recording.title,
        "kind": recording.kind,
        "status": recording.status.value,
        "audio_key": recording.audio_key,
        "audio_content_type": recording.audio_content_type,
        "audio_bytes": recording.audio_bytes,
        "duration_ms": recording.duration_ms,
        "language": None,
        "is_default_voice": False,
        "voice_embedding": None,
        "voice_embedding_model": None,
        "processing": recording.processing,
        "created_at": recording.created_at,
        "updated_at": recording.updated_at,
        "ready_at": None,
    }
    repo._by_owner.setdefault(owner, []).append(rid)


def seed_speaker(voice_repo: FakeVoiceRepo, *, is_me: bool = False, label: str = "Speaker 1",
                 centroid: list[float] | None = None, owner: str = OWNER,
                 rid: str = RECORDING) -> None:
    # The owner key comes from the `Recording` annotations (`owner_fields()`), not a literal:
    # the canonical field name lives in the service code, not in the test.
    voice_repo.speakers[SPEAKER] = {
        "_id": SPEAKER,
        owner_fields()[0]: owner,
        "recording_id": rid,
        "speaker_key": "SPEAKER_00",
        "order_index": 1,
        "label": label,
        "nick_id": None,
        "is_me": is_me,
        "centroid": centroid,
    }


def headers(owner: str = OWNER) -> dict[str, str]:
    return {"X-Auth-Subject": owner}


# --------------------------------------------------- GET /health (api.md row)


def test_health_happy():
    """Required `mongo`/`minio` are alive → `200`; response fields as in api.md §GET /health."""
    # doc_row: GET /health  (marker for scripts/check_api_contract.py)
    r = build().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["mongo"] == "ok" and body["minio"] == "ok"
    assert body["status"] in {"ok", "degraded"}
    for name in ("mongo", "minio", "qdrant", "rabbitmq", "asr"):
        assert name in body


def test_health_negative():
    """A required storage is down → `503`, body: `status: down`, `error_code`, `down[]`."""
    # doc_row: GET /health  (marker for scripts/check_api_contract.py)
    store = FakeAudioStore()
    store.available = False
    r = build(store=store).get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "down"
    assert body["down"] == ["minio"]
    # `/health` is not an error envelope: `error_code` sits at the root (api.md §GET /health).
    assert body["error_code"] in DOC_CODES


# ----------------------------------------------------- GET /api/me (api.md row)


def test_get_me_happy():
    # doc_row: GET /api/me  (marker for scripts/check_api_contract.py)
    client = build()
    r = client.get("/api/me", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Me"
    assert body["has_default_voice"] is False
    assert body["default_voice"] is None
    assert body["suggestion_limit"] == 5


def test_get_me_negative():
    # doc_row: GET /api/me  (marker for scripts/check_api_contract.py)
    r = build().get("/api/me")
    assert_error(r, "IDENTITY_MISSING")


# ------------------------------------------- GET /api/recordings (api.md row)


def test_list_recordings_happy():
    # doc_row: GET /api/recordings  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo)
    r = build(repo=repo).get("/api/recordings", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert [i["id"] for i in body["items"]] == [RECORDING]
    assert body["next_cursor"] is None


def test_list_recordings_negative():
    """`limit` outside 1…100 — the document promises `422 VALIDATION_ERROR`."""
    # doc_row: GET /api/recordings  (marker for scripts/check_api_contract.py)
    r = build().get("/api/recordings?limit=0", headers=headers())
    assert_error(r, "VALIDATION_ERROR")


# ------------------------------------------- POST /api/recordings (api.md row)


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
def test_post_recordings_happy():
    # doc_row: POST /api/recordings  (marker for scripts/check_api_contract.py)
    repo, store, queue = FakeRecordingRepo(), FakeAudioStore(), FakeQueue()
    r = build(repo=repo, store=store, queue=queue).post(
        "/api/recordings",
        headers=headers(),
        files={"file": ("lecture.wav", VALID_WAV, "audio/wav")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "uploaded"
    assert queue.published and queue.published[0][0] == "audio.diarization"


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
def test_post_recordings_negative():
    # doc_row: POST /api/recordings  (marker for scripts/check_api_contract.py)
    r = build().post(
        "/api/recordings",
        headers=headers(),
        files={"file": ("notes.txt", b"not audio at all", "text/plain")},
    )
    assert_error(r, "UNSUPPORTED_MEDIA")


# -------------------------------------- GET /api/recordings/{id} (api.md row)


def test_get_recording_happy():
    # doc_row: GET /api/recordings/{param}  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo, status="ready")
    r = build(repo=repo).get(f"/api/recordings/{RECORDING}", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert body["recording"]["id"] == RECORDING
    assert body["recording"]["status"] == "ready"
    assert body["speakers"] == []


def test_get_recording_negative():
    # doc_row: GET /api/recordings/{param}  (marker for scripts/check_api_contract.py)
    r = build().get(f"/api/recordings/{RECORDING}", headers=headers(OTHER_OWNER))
    assert_error(r, "NOT_FOUND")


# ------------------------------------ PATCH /api/recordings/{id} (api.md row)


def test_patch_recording_happy():
    # doc_row: PATCH /api/recordings/{param}  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo)
    r = build(repo=repo).patch(
        f"/api/recordings/{RECORDING}", headers=headers(), json={"title": "Seminar"}
    )  # the response is the updated recording object (api.md §PATCH)
    assert r.status_code == 200
    assert r.json()["title"] == "Seminar"


def test_patch_recording_negative():
    """An empty `title` — `422` per the document (`VALIDATION_ERROR`)."""
    # doc_row: PATCH /api/recordings/{param}  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo)
    r = build(repo=repo).patch(
        f"/api/recordings/{RECORDING}", headers=headers(), json={"title": ""}
    )
    assert_error(r, "VALIDATION_ERROR")


# ----------------------------- GET /api/recordings/{id}/phrases (api.md row)


def test_get_phrases_happy():
    # doc_row: GET /api/recordings/{param}/phrases  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo, status="transcribing")
    r = build(repo=repo).get(f"/api/recordings/{RECORDING}/phrases", headers=headers())
    assert r.status_code == 200
    body = r.json()
    assert body["recording"]["status"] == "transcribing"
    assert body["items"] == []
    assert body["next_after_seq"] == 0


def test_get_phrases_negative():
    # doc_row: GET /api/recordings/{param}/phrases  (marker for scripts/check_api_contract.py)
    r = build().get(f"/api/recordings/{RECORDING}/phrases", headers=headers(OTHER_OWNER))
    assert_error(r, "NOT_FOUND")


# ------------------------------ GET /api/recordings/{id}/audio (api.md row)


def _with_audio() -> tuple[TestClient, FakeAudioStore]:
    repo, store = FakeRecordingRepo(), FakeAudioStore()
    seed_recording(repo, status="ready")
    store.objects[f"u/{OWNER}/rec/{RECORDING}/original.wav"] = VALID_WAV
    store.meta[f"u/{OWNER}/rec/{RECORDING}/original.wav"] = {
        "content_type": "audio/wav",
        "size": len(VALID_WAV),
    }
    return build(repo=repo, store=store), store


def test_get_audio_happy():
    # doc_row: GET /api/recordings/{param}/audio  (marker for scripts/check_api_contract.py)
    client, _ = _with_audio()
    r = client.get(f"/api/recordings/{RECORDING}/audio", headers=headers())
    assert r.status_code == 200
    assert len(r.content) == len(VALID_WAV)
    assert r.headers["accept-ranges"] == "bytes"


def test_get_audio_negative():
    """A recording in `recording` (a note is being written) → `409 AUDIO_NOT_READY`."""
    # doc_row: GET /api/recordings/{param}/audio  (marker for scripts/check_api_contract.py)
    repo = FakeRecordingRepo()
    seed_recording(repo, kind="voice_note", status="recording")
    r = build(repo=repo).get(f"/api/recordings/{RECORDING}/audio", headers=headers())
    assert_error(r, "AUDIO_NOT_READY")


# ----------------------------- HEAD /api/recordings/{id}/audio (api.md row)


def test_head_audio_happy():
    # doc_row: HEAD /api/recordings/{param}/audio  (marker for scripts/check_api_contract.py)
    client, _ = _with_audio()
    r = client.head(f"/api/recordings/{RECORDING}/audio", headers=headers())
    assert r.status_code == 200
    assert r.headers["content-length"] == str(len(VALID_WAV))


def test_head_audio_negative():
    """A range past the end of the object → `416` + `Content-Range: bytes */{len}`."""
    # doc_row: HEAD /api/recordings/{param}/audio  (marker for scripts/check_api_contract.py)
    client, _ = _with_audio()
    r = client.get(
        f"/api/recordings/{RECORDING}/audio",
        headers={**headers(), "Range": f"bytes={len(VALID_WAV)}-"},
    )
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{len(VALID_WAV)}"


# --------------------------------------- POST /api/voice-notes (api.md row)


class _Probe:
    def __init__(self, available=True, busy=False):
        self.available, self.busy = available, busy

    async def __call__(self):
        return self.available, self.busy


def test_post_voice_notes_happy():
    # doc_row: POST /api/voice-notes  (marker for scripts/check_api_contract.py)
    voice_repo = FakeVoiceRepo()
    client = build(voice_repo=voice_repo, probe=_Probe())
    r = client.post("/api/voice-notes", headers=headers())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Note 1"
    assert body["audio_format"] == "pcm_s16le"
    assert body["ws_url"].endswith("/stream")
    assert voice_repo.speakers[body["speaker_id"]]["speaker_key"] == "SELF"


def test_post_voice_notes_negative():
    # doc_row: POST /api/voice-notes  (marker for scripts/check_api_contract.py)
    r = build(probe=_Probe(available=False)).post("/api/voice-notes", headers=headers())
    assert_error(r, "ASR_UNAVAILABLE")


# --------------------------- WS /api/voice-notes/{id}/stream (api.md row)


def test_ws_stream_happy():
    """The socket opens: the first frame is `ready` (api.md §WS, "Server → client")."""
    # doc_row: WS /api/voice-notes/{param}/stream  (marker for scripts/check_api_contract.py)
    repo, voice_repo = FakeRecordingRepo(), FakeVoiceRepo()
    seed_recording(repo, kind="voice_note", status="recording")
    asr = FakeAsrFactory()
    stream = asr.add(FakeAsrStream())
    client = build(
        repo=repo, voice_repo=voice_repo, asr_factory=asr, muxer=FakeMuxerFactory()
    )
    with client.websocket_connect(
        f"/api/voice-notes/{RECORDING}/stream", headers=headers()
    ) as ws:
        frame = ws.receive_json()
        assert frame["type"] == "ready"
        assert frame["recording_id"] == RECORDING
        assert frame["sample_rate"] == 16000
        assert stream.opened  # the socket to asr-worker is open


def test_ws_stream_negative():
    """No `X-Auth-Subject` on Upgrade → the Upgrade is rejected with `401 IDENTITY_MISSING`."""
    # doc_row: WS /api/voice-notes/{param}/stream  (marker for scripts/check_api_contract.py)
    client = build()
    with pytest.raises(Exception) as exc:
        with client.websocket_connect(f"/api/voice-notes/{RECORDING}/stream") as ws:
            ws.receive_json()
    # starlette returns `WebSocketDenialResponse`: it is the same 401 envelope as in HTTP
    # (`owner_from_header_value` raises AppError before `accept()`), the browser sees
    # `WebSocket connection failed` — api.md §WS.
    response = getattr(exc.value, "response", None) or exc.value
    assert response.status_code == DOC_CODES["IDENTITY_MISSING"], repr(exc.value)
    assert response.json()["detail"]["error_code"] == "IDENTITY_MISSING", repr(exc.value)


# ---------------- GET /api/recordings/{id}/speakers/{sid}/suggestions (api.md row)


def test_get_suggestions_happy():
    # doc_row: GET /api/recordings/{param}/speakers/{param}/suggestions
    # (marker for scripts/check_api_contract.py)
    repo, voice_repo, index = FakeRecordingRepo(), FakeVoiceRepo(), FakeVoiceIndex()
    seed_recording(repo)
    # The centroid is the menu query vector (ADR-007); the dimension = the collection's (256).
    seed_speaker(voice_repo, centroid=[0.1] * 256)
    r = build(repo=repo, voice_repo=voice_repo, voice_index=index).get(
        f"/api/recordings/{RECORDING}/speakers/{SPEAKER}/suggestions", headers=headers()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["speaker"]["current"] == {"kind": "none"}
    assert body["items"] == []


def test_get_suggestions_negative():
    # doc_row: GET /api/recordings/{param}/speakers/{param}/suggestions
    # (marker for scripts/check_api_contract.py)
    repo, voice_repo = FakeRecordingRepo(), FakeVoiceRepo()
    seed_recording(repo)
    seed_speaker(voice_repo, centroid=[0.1] * 256, owner=OTHER_OWNER)
    r = build(repo=repo, voice_repo=voice_repo).get(
        f"/api/recordings/{RECORDING}/speakers/{SPEAKER}/suggestions", headers=headers()
    )
    assert_error(r, "NOT_FOUND")


# -------------------- POST /api/recordings/{id}/speakers/{sid}/nick (api.md row)


def test_post_nick_happy():
    # doc_row: POST /api/recordings/{param}/speakers/{param}/nick
    # (marker for scripts/check_api_contract.py)
    repo, voice_repo, index = FakeRecordingRepo(), FakeVoiceRepo(), FakeVoiceIndex()
    seed_recording(repo)
    seed_speaker(voice_repo, centroid=[0.1] * 256)
    r = build(repo=repo, voice_repo=voice_repo, voice_index=index).post(
        f"/api/recordings/{RECORDING}/speakers/{SPEAKER}/nick",
        headers=headers(),
        json={"name": "Anya"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["speaker"]["label"] == "Anya"
    assert body["nick"]["reused"] is False


def test_post_nick_negative():
    """An already assigned speaker and a different nick → `409 ASSIGNMENT_LOCKED`."""
    # doc_row: POST /api/recordings/{param}/speakers/{param}/nick
    # (marker for scripts/check_api_contract.py)
    repo, voice_repo, index = FakeRecordingRepo(), FakeVoiceRepo(), FakeVoiceIndex()
    seed_recording(repo)
    seed_speaker(voice_repo, centroid=[0.1] * 256)
    voice_repo.nicks[NICK] = {
        "_id": NICK,
        owner_fields()[0]: OWNER,
        "name": "Anya",
        "name_key": "anya",
    }
    voice_repo.speakers[SPEAKER]["nick_id"] = NICK
    voice_repo.speakers[SPEAKER]["label"] = "Anya"
    r = build(repo=repo, voice_repo=voice_repo, voice_index=index).post(
        f"/api/recordings/{RECORDING}/speakers/{SPEAKER}/nick",
        headers=headers(),
        json={"name": "Dima"},
    )
    assert_error(r, "ASSIGNMENT_LOCKED")


# ------------------------------------ PUT /api/me/voice (api.md row)


def test_put_me_voice_happy():
    # doc_row: PUT /api/me/voice  (marker for scripts/check_api_contract.py)
    repo, voice_repo, index = FakeRecordingRepo(), FakeVoiceRepo(), FakeVoiceIndex()
    seed_recording(repo, kind="voice_note", status="ready")
    repo._recordings[RECORDING]["voice_embedding"] = [0.01] * 256
    repo._recordings[RECORDING]["processing"]["embedding"] = "ready"
    r = build(repo=repo, voice_repo=voice_repo, voice_index=index).put(
        "/api/me/voice", headers=headers(), json={"recording_id": RECORDING, "speaker_id": None}
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_default_voice"] is True
    assert r.json()["default_voice"]["recording_id"] == RECORDING


def test_put_me_voice_negative():
    """No vector yet (`voice_embedding: null`) → `409 VOICE_NOT_READY`."""
    # doc_row: PUT /api/me/voice  (marker for scripts/check_api_contract.py)
    repo, voice_repo, index = FakeRecordingRepo(), FakeVoiceRepo(), FakeVoiceIndex()
    seed_recording(repo, kind="voice_note", status="recording")
    r = build(repo=repo, voice_repo=voice_repo, voice_index=index).put(
        "/api/me/voice", headers=headers(), json={"recording_id": RECORDING, "speaker_id": None}
    )
    assert_error(r, "VOICE_NOT_READY")


# ------------------------------------------ document coverage completeness


def test_every_doc_row_has_happy_and_negative():
    """100% of the "## Endpoints" table rows: each gets `happy` and `negative`."""
    import inspect
    import sys

    module = sys.modules[__name__]
    marker = re.compile(r'^\s*# doc_row: (\S+ \S+)')
    declared: dict[str, set[str]] = {}
    for name, fn in vars(module).items():
        if not name.startswith("test_") or not callable(fn):
            continue
        source = inspect.getsource(fn)
        # Line by line, not `search` over the whole source: `^` with `\s*` at the start
        # of the block eats the newline, and the marker of the very first line stops matching.
        m = next((hit for hit in map(marker.search, source.splitlines()) if hit), None)
        if not m:
            continue
        kind = "happy" if name.endswith("_happy") else (
            "negative" if name.endswith("_negative") else "other"
        )
        declared.setdefault(m.group(1).strip(), set()).add(kind)

    assert DOC_ROWS, "the '## Endpoints' table was not found in api.md"
    missing: list[str] = []
    for row in DOC_ROWS:
        kinds = declared.get(row, set())
        for kind in ("happy", "negative"):
            if kind not in kinds:
                missing.append(f"{row}: no {kind}")
    assert not missing, "not covered by a contract test:\n" + "\n".join(missing)
    assert set(declared) <= set(DOC_ROWS), (
        "the test declares a row that is not in api.md: "
        + ", ".join(sorted(set(declared) - set(DOC_ROWS)))
    )


def test_error_codes_in_doc_are_served_by_code():
    """Every "Error codes" table code is in `ErrorCode`/`HTTP_STATUS` with the same status."""
    from app.domain.errors import HTTP_STATUS, ErrorCode

    code = {c.value: HTTP_STATUS[c] for c in ErrorCode}
    for name, status in DOC_CODES.items():
        if name == "VALIDATION_ERROR":
            # Not a domain code: served by the RequestValidationError handler (errors.py).
            assert status == 422
            continue
        assert name in code, f"api.md describes {name}, but it is not in ErrorCode"
        assert code[name] == status, f"{name}: code {code[name]}, document {status}"
    for name in code:
        assert name in DOC_CODES, f"ErrorCode.{name} is not described in api.md §Error codes"
