"""Worker logging wiring: `install` sets up JSON and does not duplicate handlers."""

from __future__ import annotations

import json
import logging

from app.logging import install, level_from_env


def test_install_is_idempotent_and_emits_json(tmp_path, monkeypatch):
    log_file = tmp_path / "w.ndjson"
    monkeypatch.setenv("ASR_LOG_STREAM", str(log_file))
    install(service="diarizer")
    install(service="diarizer")  # repeated call from lifespan
    handlers = [h for h in logging.getLogger().handlers if getattr(h, "_asr_json", False)]
    assert len(handlers) == 1, "a second handler would duplicate lines"

    logging.getLogger("app.test").info(
        "job_start recording=%s owner=%s job=%s stage=diarization",
        "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21",
        "9f1d2c33",
        "7d1e2f30",
    )
    for handler in handlers:
        stream = getattr(handler, "stream", None)
        if stream is not None:
            stream.flush()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["service"] == "diarizer"
    assert record["recording_id"] == "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"
    assert record["owner"] == "9f1d2c33"
    assert record["stage"] == "diarization"

    for handler in handlers:
        logging.getLogger().removeHandler(handler)
        stream = getattr(handler, "stream", None)
        if stream is not None:
            stream.close()


def test_level_from_env(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert level_from_env() == logging.INFO
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert level_from_env() == logging.DEBUG
    monkeypatch.setenv("LOG_LEVEL", "nonsense")
    assert level_from_env() == logging.INFO
