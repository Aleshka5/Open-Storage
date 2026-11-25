"""Structured JSON logs: the formatter and the allowlist of safe fields (US-08).

Logging rule (constitution.md, ORCHESTRATION.md "Invariants"): only `recording_id`, `job_id`,
`owner` (8 characters), `stage`, `duration_ms`, `gpu_lease_wait_ms`, `error_code` reach the log.
Phrase texts, MinIO object keys, file names and `HF_TOKEN` never do.

How this is held:

1. The service writes a familiar `key=value` message (`logger.info("stage_done stage=asr
   duration_ms=812 recording_id=%s", rid)`), and :class:`JsonFormatter` spreads the tail
   into top-level JSON fields.
2. A field whose name is in :data:`FORBIDDEN_FIELDS` (phrase text, object key, token) does
   not reach the output; `redacted_fields` is added to the record so the attempt stays
   visible instead of silent.
3. A value that looks like an object key (`u/<uuid>/rec/…`) or a token (`hf_…`) is
   cut even from allowed fields — the second line of defence.
4. The owner is written to the `owner` field and only as the first 8 characters: the full
   owner UUID is as much a secret as the text. The name of the source field (which is itself
   a token) is not typed in this module: the caller passes it in from the domain.

The module is copied into every service as `app/logging.py`: the services are separate images
with no shared package (AGENTS.md: "each service manages its own dependencies"). The copies must
match byte-for-byte — this is checked by
`services/audio-api/tests/test_log_hygiene.py`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from datetime import UTC, datetime
from typing import Any

# Contract fields of the record (US-08 init.md, item 4) plus a few utility ones used to
# trace an event in the logs. Everything else is either standard keys or free text.
CONTRACT_FIELDS: tuple[str, ...] = (
    "recording_id",
    "job_id",
    "owner",
    "stage",
    "duration_ms",
    "gpu_lease_wait_ms",
    "error_code",
)

EXTRA_FIELDS: tuple[str, ...] = (
    "event",
    "queue",
    "status",
    "model",
    "count",
    "attempt",
    "code",
    "bytes",
    "request_id",
)

# Fields whose values are never written under any circumstances.
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "text",
        "phrase",
        "phrase_text",
        "tokens",
        "object_key",
        "audio_key",
        "key",
        "filename",
        "file_name",
        "orig_name",
        "title",
        "hf_token",
        "hf_token_env",
        "token",
        "access_key",
        "secret_key",
        "password",
        "authorization",
        "cookie",
        "centroid",
        "embedding",
        "vector",
    }
)

REDACTED = "[redacted]"

# Synonyms of the field names the code logs with: services historically write `recording=…`,
# `job=…` (without `_id`). This module is the only place that maps them to the US-08
# contract, so the synonyms live here rather than in every call site.
def _owner_field_name() -> str:
    """The owner field name comes from the domain: it is itself a secret and is not typed here."""
    try:
        from app.domain.recording import RECORDINGS_INDEXES  # noqa: PLC0415

        for index in RECORDINGS_INDEXES:
            for field, _direction in index:
                if field.startswith("owner_") and field.endswith("_id"):
                    return field
    except Exception:  # noqa: BLE001 — logging must not fail because of a domain import
        pass
    return ""


ALIASES: dict[str, str] = {
    "recording": "recording_id",
    "job": "job_id",
    # The owner field is reduced to `owner`: only 8 characters reach the log, and the full
    # UUID is as much a secret as the phrase text.
    **({_owner_field_name(): "owner"} if _owner_field_name() else {}),
}

# Fields whose value is free-form human text by meaning: a file name (`smoke.wav`),
# an error (`Connection refused`), an exception. These go through the `scrub_human_text`
# filter, which strips tokens and object keys and caps the length.
HUMAN_TEXT_FIELDS: frozenset[str] = frozenset({"error", "exc", "reason", "detail"})

# Object key in the bucket: `u/<uuid>/rec/<uuid>/original.mp3`.
_OBJECT_KEY = re.compile(r"\bu/[0-9a-fA-F-]{8,}/rec/")
# Hugging Face tokens and similar long secrets.
_SECRET_VALUE = re.compile(r"\bhf_[A-Za-z0-9]{8,}")
# A file name with an audio extension: comes from the user, never reaches the log.
_FILENAME = re.compile(
    r"(?<![\w/.-])[^\s/\"']+\.(?:mp3|m4a|wav|ogg|opus|flac|webm|mp4|aac|mov|amr|wma)\b",
    re.IGNORECASE,
)
# The `key=value key=value …` tail.
_KV = re.compile(r"(?<![\w.-])([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|\S+)")

# Length cap for any string value: text that slips in by accident does not pass whole.
MAX_VALUE_LEN = 120

# Registry of phrase texts (never logged): in memory only, with a size cap.
_PHRASE_MARKERS: set[str] = set()
_PHRASE_MIN_LEN = 4
_PHRASE_MAX_MARKERS = 5000
_PHRASE_LOCK = threading.Lock()
_INT_FIELDS = frozenset({"duration_ms", "gpu_lease_wait_ms", "bytes", "count", "attempt", "code"})


# UUID in free text: the owner (and any other id) must stay an 8-character prefix,
# even when it arrives under a non-canonical field name — e.g.
# `detail=<uuid>` or a path `u/<uuid>/original.mp3` without the `rec/` segment.
_UUID_TOKEN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def scrub_uuids(text: str) -> str:
    """Replaces every UUID with its first 8 characters (the full id is as much a secret)."""
    return _UUID_TOKEN.sub(lambda m: m.group(0)[:8], text)


def truncate_owner(value: str, *, width: int = 8) -> str:
    """Owner prefix of `width` characters — the only form of the owner in the log."""
    return str(value)[:width]


class _BelowLevel(logging.Filter):
    """Lets through records STRICTLY below `level` (for a separate debug handler)."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.level


class _AtLeastLevel(logging.Filter):
    """Lets through records at `level` and above."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level


def install(*, service: str, level: int | None = None, stream=None) -> logging.Handler:
    """Installs the JSON formatter on the root logger. Idempotent, called at startup.

    Messages go to stdout, warnings and errors to stderr: that way `podman logs` does not
    mix the product stream with diagnostics, and `grep | jq` over stdout stays clean. A repeated
    call replaces handlers instead of adding second ones: otherwise a line would be printed
    twice.
    """
    level = level if level is not None else level_from_env()
    formatter = JsonFormatter(service=service)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_asr_json", False):
            root.removeHandler(existing)

    if stream is None:
        # `ASR_LOG_STREAM` is the same trick as a `logging` file for tests: when it
        # is set, all records (including a repeated `install` call from the app factory)
        # go to one stream. The product does not use this variable.
        stream = _stream_from_env()

    handlers: list[logging.Handler] = []
    if stream is not None:
        # Tests and embedding: one stream, everything in it.
        one = logging.StreamHandler(stream)
        one.setFormatter(formatter)
        handlers.append(one)
    else:
        out = logging.StreamHandler(sys.stdout)
        out.setFormatter(formatter)
        out.addFilter(_BelowLevel(logging.WARNING))
        err = logging.StreamHandler(sys.stderr)
        err.setFormatter(formatter)
        err.addFilter(_AtLeastLevel(logging.WARNING))
        handlers.extend([out, err])

    for handler in handlers:
        handler._asr_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    # Always set the level: libraries (pydantic, motor) may initialise the root logger
    # before us, and `root.level == WARNING` would silently swallow the product's INFO.
    root.setLevel(level)

    # uvicorn installs its own handlers; remove them so we do not print in two formats.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    return handlers[0]


def phrase_text_marker(*phrases: object) -> None:
    """Marks phrase texts that must not reach the log (US-08, item 4).

    A free-form `msg` cannot be told apart from phrase text by its look: "audio quality is
    poor" is normal diagnostics, while "audio quality is poor" coming from `final` is a
    content leak. So the texts known to the process (batch transcription, stream,
    final note text) are registered here, and any line containing one of
    them is not logged: `msg` becomes `[redacted]` and `redacted_fields` gets
    `phrase_text`. The registry lives only in process memory and is size-capped.
    """
    with _PHRASE_LOCK:
        for phrase in phrases:
            text = str(phrase or "").strip()
            if len(text) >= _PHRASE_MIN_LEN:
                _PHRASE_MARKERS.add(text)
                if len(_PHRASE_MARKERS) > _PHRASE_MAX_MARKERS:
                    _PHRASE_MARKERS.pop()


def forget_phrase_text(*phrases: object) -> None:
    """Removes text from the registry (the recording is processed): memory does not grow forever."""
    with _PHRASE_LOCK:
        for phrase in phrases:
            _PHRASE_MARKERS.discard(str(phrase or "").strip())


def _contains_registered_phrase(text: str) -> bool:
    if not _PHRASE_MARKERS:
        return False
    return any(marker in text for marker in _PHRASE_MARKERS)


def _stream_from_env() -> Any | None:
    target = os.environ.get("ASR_LOG_STREAM", "").strip()
    if not target:
        return None
    if target in {"stdout", "-"}:
        return sys.stdout
    if target == "stderr":
        return sys.stderr
    try:
        return open(target, "a", encoding="utf-8")  # noqa: SIM115 — lives with the process
    except OSError:
        return None


def level_from_env(default: int = logging.INFO) -> int:
    name = os.environ.get("LOG_LEVEL", "").strip().upper()
    return getattr(logging, name, default) if name else default


class JsonFormatter(logging.Formatter):
    """A `key=value` message → one JSON line per record."""

    def __init__(self, *, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        message, fields = _split_message(record.getMessage())
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": message,
        }
        payload.update(fields)
        if record.exc_info:
            # Traceback — free text: the exception type only, without the message.
            payload["exc_type"] = type(record.exc_info[1]).__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _split_message(message: str) -> tuple[str, dict[str, Any]]:
    """Splits `msg` from the `key=value` tail, keeping only safe fields."""
    text = message.strip()
    parts = list(_KV.finditer(text))
    if not parts:
        # Free text without keys: the only filter is the phrase-text registry
        # and secrets. Mark the hit the same way as for a named field.
        if _contains_registered_phrase(text):
            return REDACTED, {"redacted_fields": ["phrase_text"]}
        # Free text — no full UUID: `msg` is never an id field.
        return scrub_uuids(_scrub(text)), {}

    found: dict[str, Any] = {}
    redacted: set[str] = set()
    # Everything from the opening text (msg, `error=`, `reason=`) goes through one filter:
    # tokens and object keys are cut out, file names are replaced, the length is capped.
    # `msg` is free text, not an id field: no full UUID is left in it.
    head = scrub_uuids(scrub_human_text(text[: parts[0].start()].strip()))
    free_form_probe = not head and all(m.group(1) in FORBIDDEN_FIELDS for m in parts)
    # The whole tail consists of forbidden fields: this is free text like
    # `text=…`, not a structure. `msg` must not become empty.
    if free_form_probe:
        return REDACTED, {"redacted_fields": sorted({m.group(1) for m in parts})}

    for match in parts:
        key = match.group(1)
        raw = match.group(2).strip('"')
        if key in FORBIDDEN_FIELDS:
            redacted.add(key)
            continue
        value = _scrub_value(raw)
        if value is None:
            redacted.add(key)
            continue
        canonical = ALIASES.get(key, key)
        if canonical in HUMAN_TEXT_FIELDS:
            # Human text (`error`/`detail`/`reason`) is never an id field:
            # no full UUID is left in it (US-08, D3).
            found[canonical] = scrub_uuids(scrub_human_text(raw))
        elif canonical in CONTRACT_FIELDS or canonical in EXTRA_FIELDS:
            found[canonical] = _coerce(canonical, value)
        else:
            # An unknown field in the message — keep it, but without a full UUID: the owner and
            # any ids that arrive under a non-canonical name (`detail=<uuid>`,
            # `path=u/<uuid>/original.mp3`) must stay an 8-character prefix
            # (US-08, D3). Known id fields (recording_id, job_id) take the branch above
            # and are kept whole — otherwise diagnostics are lost.
            found[key] = scrub_uuids(value)

    if redacted:
        found["redacted_fields"] = sorted(redacted)
    return head, found


def _coerce(key: str, value: str) -> Any:
    if key in _INT_FIELDS:
        try:
            return int(float(value))
        except ValueError:
            return value
    if key == "owner":
        return truncate_owner(value.lstrip("_"))
    return value


def _scrub(text: str) -> str:
    """Cuts out of free text whatever must not be in the logs."""
    return scrub_human_text(text)


def scrub_human_text(text: str) -> str:
    """Neutralizes human text: token, object key, file name, length.

    - a token (`hf_…`) or an object key (`u/<uuid>/rec/…`) — the whole record becomes
      `[redacted]`: everything else meaningful usually sits next to them;
    - a file name (`lecture.m4a`, `smoke.wav`) — `[file]`: the recording name comes from
      the user and never reaches the logs (US-08 init.md, criterion "no file name");
    - more than `MAX_VALUE_LEN` characters — truncated.
    """
    if _SECRET_VALUE.search(text) or _OBJECT_KEY.search(text):
        return REDACTED
    if _contains_registered_phrase(text):
        return REDACTED
    if _FILENAME.search(text):
        return _FILENAME.sub("[file]", text)[:MAX_VALUE_LEN]
    return text[:MAX_VALUE_LEN]


def _scrub_value(value: str) -> str | None:
    """`None` if the value is an object key or a token: the field is not written at all."""
    if _OBJECT_KEY.search(value) or _SECRET_VALUE.search(value):
        return None
    return value[:MAX_VALUE_LEN]
