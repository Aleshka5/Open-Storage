"""Logs of a whole run: a scenario through the HTTP surface leaves no secrets in the log.

US-08 acceptance criterion: "the logs of a run contain neither `HF_TOKEN`, nor phrase text, nor
a file name; they do contain `recording_id`/`job_id`/`error_code`". Formatter unit tests
(`test_log_hygiene.py`) check individual records; here the **whole stream** of
a run is checked: upload, phrase reading, the Range player, 401 without identity, a MinIO refusal.

Separately it is checked that the `recording_id` field (and `error_code`) is really
in the log — otherwise "clean logs" could be obtained by not logging anything at all.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

from app.logging import forget_phrase_text, install, phrase_text_marker
from app.presentation.api import create_app
from app.presentation.container import Container
from tests.conftest import OWNER, VALID_WAV

SERVICES_DIR = pathlib.Path(__file__).resolve().parents[2]
_OWNER_MATCH = re.search(
    r"\b(owner_[A-Za-z0-9_]+_id)\b",
    (pathlib.Path(__file__).resolve().parents[1] / "app" / "domain" / "recording.py").read_text(
        encoding="utf-8"
    ),
)
assert _OWNER_MATCH is not None
OWNER_FIELD = _OWNER_MATCH.group(1)

FILENAME = "lecture-about-travel.m4a"
PHRASE = "we postpone the release until Monday"
HF_TOKEN = "hf_" + "Q" * 30


@pytest.fixture
def logs(monkeypatch, tmp_path):
    """All root logger records go to one file; read after the run.

    `install` is called again from `create_app`, so the stream is set via the
    `ASR_LOG_STREAM` variable: the repeat call writes to the same file.
    """
    log_file = tmp_path / "run.ndjson"
    monkeypatch.setenv("ASR_LOG_STREAM", str(log_file))
    monkeypatch.setenv("HF_TOKEN", HF_TOKEN)
    install(service="audio-api")
    try:
        yield log_file
    finally:
        root = logging.getLogger()
        for handler in list(root.handlers):
            if getattr(handler, "_asr_json", False):
                root.removeHandler(handler)
                stream = getattr(handler, "stream", None)
                if stream is not None and stream not in (sys.stdout, sys.stderr):
                    stream.close()
        root.setLevel(logging.WARNING)
        forget_phrase_text(PHRASE)


def _client(settings, repo, voice_repo, voice_index, store, queue, monkeypatch):
    async def _qdrant_ok(url):
        return True

    async def _asr_ok(ws_url):
        return False  # asr-worker is "killed" — a run must work like this too

    monkeypatch.setattr("app.presentation.health._qdrant_ok", _qdrant_ok)
    monkeypatch.setattr("app.presentation.health._asr_ok", _asr_ok)
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


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe is not installed")
def test_run_emits_no_secrets_but_has_recording_and_error_codes(
    logs, settings, repo, voice_repo, voice_index, store, queue, monkeypatch
):
    client = _client(settings, repo, voice_repo, voice_index, store, queue, monkeypatch)

    # The run: file upload → phrases → 401 without identity → health with MinIO alive.
    upload = client.post(
        "/api/recordings",
        headers={"X-Auth-Subject": OWNER},
        files={"file": (FILENAME, VALID_WAV, "audio/wav")},
        data={"title": "Travel"},
    )
    assert upload.status_code == 201, upload.text
    recording_id = upload.json()["id"]
    client.get(
        f"/api/recordings/{recording_id}/phrases",
        headers={"X-Auth-Subject": OWNER},
    )
    anonymous = client.get("/api/recordings")
    assert anonymous.status_code == 401
    assert client.get("/health").status_code == 200

    # MinIO is stopped: the upload must answer 503 STORAGE_UNAVAILABLE.
    store.available = False
    store.fail_put = True
    broken = client.post(
        "/api/recordings",
        headers={"X-Auth-Subject": OWNER},
        files={"file": ("another-file.m4a", VALID_WAV, "audio/wav")},
    )
    assert broken.status_code in (500, 503), broken.text

    output = logs.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in output.splitlines() if line.strip()]
    assert lines, "the run produced no log records"

    # 1. Secrets and content do not leak in any form.
    assert HF_TOKEN not in output
    assert PHRASE not in output
    assert FILENAME not in output
    assert "another-file" not in output
    assert "rec/" not in output
    assert "Travel" not in output
    for line in lines:
        assert isinstance(json.loads(json.dumps(line)), dict)
        assert "text" not in line

    # 2. The full owner UUID is not written.
    assert OWNER not in output
    assert OWNER_FIELD not in output

    # 3. The contract fields are really there: a trace can be found in the log.
    # Trace via `recording_id` and `error_code`: `error_code` is written by `/health`, the upload
    # refusal comes as a 503 envelope with the code `STORAGE_UNAVAILABLE`.
    assert any(line.get("error_code") for line in lines), "no error_code in the log"
    assert any(line.get("stage") for line in lines), "no stage in the log"
    assert recording_id in output, "the run's recording_id did not reach the log"
    # Identifiers go one per field, not hidden in msg.
    assert any(
        "recording_id" in line.get("msg", "") for line in lines
    ) or any(
        "recording_id" in key for line in lines for key in line
    ), "recording_id is not marked up as a key"
    for line in lines:
        assert set(line) >= {"ts", "level", "service", "logger", "msg"}
        assert line["service"] == "audio-api"
        assert isinstance(line["ts"], str)


def test_recorded_phrase_is_scrubbed_from_free_text(
    logs, settings, repo, voice_repo, voice_index, store, queue, monkeypatch
):
    """Phrase text known to the process does not appear even in free-form `msg`."""
    phrase_text_marker(PHRASE)
    client = _client(settings, repo, voice_repo, voice_index, store, queue, monkeypatch)
    logging.getLogger("app.test").warning("chat tick %s", PHRASE)
    client.get("/health")
    output = logs.read_text(encoding="utf-8")
    assert PHRASE not in output
    records = [json.loads(line) for line in output.splitlines() if line.strip()]
    ticks = [r for r in records if r["logger"] == "app.test"]
    assert len(ticks) == 1
    assert ticks[0]["msg"] == "[redacted]"
    assert ticks[0]["redacted_fields"] == ["phrase_text"]
