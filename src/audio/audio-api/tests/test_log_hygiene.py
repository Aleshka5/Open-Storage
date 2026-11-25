"""Log hygiene (US-08, item 4): a record holds no secrets, phrase text or object keys.

Checked on real log records (`JsonFormatter`, not mocks):

1. Format — one JSON line per record, `ts`/`level`/`service`/`msg` in place.
2. Contract fields are spread into keys: `recording_id`, `job_id`, `owner`
   (exactly 8 characters), `stage`, `duration_ms`, `gpu_lease_wait_ms`, `error_code`.
3. `HF_TOKEN`, token-like values, MinIO object keys (`u/<uuid>/rec/…`) and
   file names appear neither in `msg` nor in the fields.
4. A field with a forbidden name (`text`, `phrase_text`, `object_key`, `hf_token`…)
   is dropped: the value is not in the output, and `redacted_fields` shows the attempt.
5. The full owner UUID never reaches the log — only an 8-character prefix.

The owner field names are not typed by hand in this test: `OWNER_FIELD` comes from the domain
(`app/domain/recording.py`), otherwise the test itself would become a source of a corrupted literal.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import sys

import pytest

from app.logging import (
    CONTRACT_FIELDS,
    JsonFormatter,
    forget_phrase_text,
    install,
    phrase_text_marker,
    truncate_owner,
)

SERVICES_DIR = pathlib.Path(__file__).resolve().parents[2]
# The owner field name is a secret token: we take it from the domain, not type it by hand.
_OWNER_MATCH = re.search(
    r"\b(owner_[A-Za-z0-9_]+_id)\b",
    (pathlib.Path(__file__).resolve().parents[1] / "app" / "domain" / "recording.py").read_text(
        encoding="utf-8"
    ),
)
assert _OWNER_MATCH is not None, "no owner field name found in the domain"
OWNER_FIELD = _OWNER_MATCH.group(1)
OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
RECORDING = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"
JOB = "7d1e2f30-4a5b-4c6d-8e9f-0a1b2c3d4e5f"

# A phrase a person actually says (text from the scenario — it must not leak).
PHRASE_TEXT = "secret: the email password is in the top drawer"
SECRET = "hf_" + "A" * 24
OBJECT_KEY = f"u/{OWNER}/rec/{RECORDING}/original.mp3"
FILENAME = "lecture-about-taxes.m4a"


@pytest.fixture
def sink(monkeypatch, tmp_path):
    """All root logger records go to one file (read after the test).

    The stream is set via `ASR_LOG_STREAM`: `install` is called again from `create_app`,
    and without that repeat call the output would go to stdout.
    """
    log_file = tmp_path / "test.ndjson"
    monkeypatch.setenv("ASR_LOG_STREAM", str(log_file))
    install(service="audio-api")
    logger = logging.getLogger("tests.log_hygiene")
    try:
        yield log_file, logger
    finally:
        root = logging.getLogger()
        for existing in list(root.handlers):
            if getattr(existing, "_asr_json", False):
                root.removeHandler(existing)
                stream = getattr(existing, "stream", None)
                if stream is not None and stream not in (sys.stdout, sys.stderr):
                    stream.close()
        root.setLevel(logging.WARNING)


def _records(log_file) -> list[dict]:
    text = log_file.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _text(log_file) -> str:
    return log_file.read_text(encoding="utf-8")


def test_format_is_single_json_line(sink):
    buffer, logger = sink
    logger.info("stage_done stage=diarization")
    lines = _text(buffer).strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) >= {"ts", "level", "service", "logger", "msg"}
    assert record["service"] == "audio-api"
    assert record["level"] == "info"
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$", record["ts"])


def test_contract_fields_are_split_into_keys(sink):
    buffer, logger = sink
    logger.info(
        "job_done stage=transcription duration_ms=%d gpu_lease_wait_ms=%d "
        "recording_id=%s job_id=%s owner=%s error_code=NONE",
        812,
        15,
        RECORDING,
        JOB,
        OWNER,
    )
    (record,) = _records(buffer)
    assert record["stage"] == "transcription"
    assert record["duration_ms"] == 812
    assert record["gpu_lease_wait_ms"] == 15
    assert record["recording_id"] == RECORDING
    assert record["job_id"] == JOB
    assert record["error_code"] == "NONE"
    # The owner is only an 8-character prefix, not the UUID.
    assert record["owner"] == OWNER[:8]
    assert len(record["owner"]) == 8
    assert OWNER not in _text(buffer)
    for field in CONTRACT_FIELDS:
        assert field in record


def test_phrase_text_never_reaches_the_log(sink):
    """Text recognized by asr-worker is registered — and does not reach the log."""
    buffer, logger = sink
    phrase_text_marker(PHRASE_TEXT)  # what stream_handler does after transcribe
    try:
        # This is what a "convenient" log would look like: gathering context into a string.
        logger.info("final_text text=%s recording_id=%s", PHRASE_TEXT, RECORDING)
        logger.info("phrase_text=%s", PHRASE_TEXT.replace(" ", "_"))
        logger.warning("asr final %s", PHRASE_TEXT)
    finally:
        forget_phrase_text(PHRASE_TEXT)
    assert PHRASE_TEXT not in _text(buffer)
    records = _records(buffer)
    assert all("text" not in r for r in records)
    # The first record kept the identifier but not the text.
    assert records[0]["recording_id"] == RECORDING
    assert records[2]["msg"] == "[redacted]"


def test_unregistered_text_is_not_blanket_redacted(sink):
    """The other side: ordinary text diagnostics stays readable."""
    buffer, logger = sink
    logger.warning('muxer_failed error="ffmpeg returned code 1"')
    (record,) = _records(buffer)
    assert record["msg"] == "muxer_failed"
    assert record["error"] == "ffmpeg returned code 1"


def test_forbidden_field_names_are_dropped_and_reported(sink):
    buffer, logger = sink
    logger.warning("job_failed text=%s recording_id=%s error_code=INTERNAL", PHRASE_TEXT, RECORDING)
    (record,) = _records(buffer)
    assert record["recording_id"] == RECORDING
    assert record["error_code"] == "INTERNAL"
    assert record["redacted_fields"] == ["text"]


def test_object_keys_and_tokens_never_emitted(sink):
    buffer, logger = sink
    logger.warning("object_key=%s recording_id=%s", OBJECT_KEY, RECORDING)
    logger.error("upload_failed key=%s filename=%s", OBJECT_KEY, FILENAME)
    logger.error("login hf_token=%s", SECRET)
    logger.error("hf token %s", SECRET)
    out = _text(buffer)
    assert OBJECT_KEY not in out
    assert "rec/" not in out
    assert SECRET not in out
    assert FILENAME not in out


def test_hf_token_from_environment_never_logged(sink, monkeypatch):
    """Even if the token got into the format string, it is not in the log."""
    buffer, logger = sink
    token = "hf_" + "Z" * 34
    monkeypatch.setenv("HF_TOKEN", token)
    logger.warning("model_load_failed hf_token_env=%s recording_id=%s", token, RECORDING)
    logger.warning("model auth failed for %s", token)
    assert token not in _text(buffer)
    records = _records(buffer)
    assert len(records) == 2
    assert records[0]["recording_id"] == RECORDING
    assert "hf_token_env" in records[0].get("redacted_fields", [])


def test_owner_uuid_is_truncated_by_helper():
    assert truncate_owner(OWNER) == OWNER[:8]
    assert truncate_owner("ab") == "ab"


def test_real_owner_field_is_truncated_in_formatted_record():
    """The owner field under ITS real name is also truncated to 8 characters.

    Regression: `_coerce` only truncated the `owner` alias, and a record with the canonical
    owner field name went to the log whole — the full owner UUID got into the logs.
    """
    formatter = JsonFormatter(service="audio-api")
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, f"evt {OWNER_FIELD}={OWNER} stage=upload", (), None
    )
    payload = json.loads(formatter.format(record))

    assert OWNER not in json.dumps(payload), "the full owner UUID got into the log"
    assert payload.get("owner") == OWNER[:8]
    assert payload.get("stage") == "upload"


def test_formatter_truncates_long_values():
    """An accidentally long value in an allowed field does not pass whole."""
    formatter = JsonFormatter(service="audio-api")
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "note event=%s", ("x" * 500,), None
    )
    payload = json.loads(formatter.format(record))
    assert len(payload["event"]) <= 120


def test_logging_module_is_identical_in_all_services():
    """The `app/logging.py` copies must be identical: otherwise the format drifts."""
    copies = {
        service: (SERVICES_DIR / service / "app" / "logging.py").read_text(encoding="utf-8")
        for service in ("audio-api", "diarizer", "asr-worker")
    }
    reference = copies["audio-api"]
    for service, text in copies.items():
        assert text == reference, f"app/logging.py in {service} differs from audio-api"


def test_handlers_emit_no_phrase_text_in_source():
    """Log wiring in the services: no `logger.*` passes phrase text.

    The rule is checked against the sources: dangerous variables (`text`, `phrase_text`,
    `centroid`, `audio_key`) must not appear in `logger` arguments.
    """
    forbidden_args = ("text=", "phrase_text=", "centroid=", "audio_key=", "norm_key=")
    offenders: list[str] = []
    pattern = re.compile(r"logger\.\w+\(([^)]*)\)", re.S)
    for path in SERVICES_DIR.glob("*/app/**/*.py"):
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            args = match.group(1)
            for bad in forbidden_args:
                if bad in args:
                    line = source.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(SERVICES_DIR)}:{line}: {bad}")
    assert not offenders, "text/object key in logs:\n" + "\n".join(offenders)


def test_full_uuid_never_leaks_from_non_canonical_fields():
    """The full UUID never leaks under any field name (US-08, D3).

    Regression: only the canonical `owner` alias was truncated; `detail=<uuid>`, the path
    `u/<uuid>/original.mp3` without the `rec/` segment and a UUID in free text went through
    whole — against the README "the full owner UUID is never in the log".
    """
    formatter = JsonFormatter(service="audio-api")
    for msg in (f"detail={OWNER}", f"path=u/{OWNER}/original.mp3", f"seen {OWNER}"):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, (), None)
        out = formatter.format(record)
        assert OWNER not in out, f"the full UUID leaked: {out}"
        assert OWNER[:8] in out  # the prefix stays — otherwise diagnostics is lost


def test_diagnostics_survive_redaction():
    """The redactor must not erase everything: the error cause stays readable."""
    formatter = JsonFormatter(service="audio-api")
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "muxer_failed error=ffmpeg code=1", (), None
    )
    payload = json.loads(formatter.format(record))
    assert payload["msg"] == "muxer_failed"
    assert payload.get("error") == "ffmpeg"
