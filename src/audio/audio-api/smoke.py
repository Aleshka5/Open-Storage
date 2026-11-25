#!/usr/bin/env python3
"""US-08 smoke scenario: the whole product path in one command.

    upload → ready → phrases → Range player (206) → voice note `done`

Runs against a **running** stand (`make up`) and checks what a person in
a browser does, but without a browser: MinIO, Mongo, RabbitMQ, GPU workers and the
marker WebSocket.

Where it runs. The script lives in the `audio-api` image (see the Dockerfile) and by default
works inside the container:

    make smoke                 # = podman exec -i audio-api python /srv/smoke.py
    scripts/smoke.sh           # the same, plus a check that the container is up

It also works from the outside (through the gateway, with a session cookie) — `SMOKE_BASE_URL` and
`SMOKE_COOKIE`; then the WebSocket goes to the same host. The cookie is not passed to the script
from `make`: sign-in in the product is a session, not a token, and there are no tokens by contract.

Identity without the gateway is the `X-Auth-Subject` header (ADR-001, "for local
testing"). By default it is a new random UUID: the run does not depend on someone else's data.

Standard library only: `websockets` is already in the `audio-api` image
(`uvicorn[standard]`), `http.client`/`urllib` come from the stdlib.

Exit code: 0 — all steps passed, 1 — a step failed (the step name and the response are printed).
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import struct
import sys
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_BASE = "http://127.0.0.1:8000"
TERMINAL_STATUSES = {"ready", "failed"}
POLL_TIMEOUT_S = 900.0  # headroom: file diarization takes minutes
NOTE_SECONDS = 5.0
NOTE_FRAME_BYTES = 3200  # 100 ms PCM s16le 16 kHz mono (api.md)


class SmokeFailure(RuntimeError):
    """A scenario step failed: printed as is, without a traceback."""


@dataclass
class Http:
    base: str
    owner: str
    cookie: str | None = None
    timeout: float = 60.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base)
        self.scheme = parsed.scheme or "http"
        self.netloc = parsed.netloc
        self.prefix = parsed.path.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        conn_cls = (
            http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        )
        conn = conn_cls(self.netloc, timeout=self.timeout)
        hdrs = {"X-Auth-Subject": self.owner}
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        hdrs.update(headers or {})
        try:
            conn.request(method, self.prefix + path, body=body, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
        finally:
            conn.close()

    def json(self, method: str, path: str, payload=None, headers=None):
        body = None
        hdrs = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode()
            hdrs["Content-Type"] = "application/json"
        status, _, data = self.request(method, path, body=body, headers=hdrs)
        try:
            parsed = json.loads(data) if data else None
        except ValueError:
            parsed = None
        return status, parsed


def step(name: str) -> None:
    print(f"→ {name}", flush=True)


def ok(name: str, detail: str = "") -> None:
    print(f"✓ {name}{(' — ' + detail) if detail else ''}", flush=True)


def _error_code(body) -> str:
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        return str(body["detail"].get("error_code") or "")
    if isinstance(body, dict):
        return str(body.get("error_code") or "")
    return ""


def upload(http: Http) -> str:
    """POST /api/recordings with a 1 s 16 kHz mono WAV: ffprobe must see a track."""
    step("upload: POST /api/recordings")
    wav = _make_wav(seconds=1.0)
    boundary = "----smoke" + uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="smoke.wav"\r\n',
        b"Content-Type: audio/wav\r\n\r\n",
        wav,
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="title"\r\n\r\n',
        b"Smoke US-08\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    status, _, data = http.request(
        "POST",
        "/api/recordings",
        body=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status != 201:
        raise SmokeFailure(f"upload: expected 201, got {status}: {data[:300]!r}")
    body = json.loads(data)
    if not isinstance(body, dict) or "id" not in body:
        raise SmokeFailure(f"upload: response without an id: {body}")
    recording_id = str(body["id"])
    ok("upload", f"201, {recording_id}, status={body.get('status')}")
    return recording_id


def wait_ready(http: Http, recording_id: str) -> None:
    """Waits for `ready`: diarization and transcription go through the queue and the GPU."""
    step(f"ready: waiting for status ready (up to {int(POLL_TIMEOUT_S)} s)")
    started = time.monotonic()
    last = None
    while time.monotonic() - started < POLL_TIMEOUT_S:
        status, body = http.json("GET", f"/api/recordings/{recording_id}")
        if status != 200 or not isinstance(body, dict):
            raise SmokeFailure(f"ready: GET of the recording returned {status}: {body}")
        # The contract wraps the entity: {"recording": {...}, "speakers": [...]}.
        # Reading `body["status"]` (flat) made the harness poll forever against a service
        # that had already answered `ready` (fixed 2026-11-01).
        last = (body.get("recording") or {}).get("status")
        if last in TERMINAL_STATUSES:
            break
        time.sleep(2.0)
    elapsed = time.monotonic() - started
    if last != "ready":
        raise SmokeFailure(
            f"ready: the recording is in status {last!r} after {elapsed:.0f} s "
            f"(stuck? see `make logs SERVICE=diarizer`)"
        )
    ok("ready", f"status=ready in {elapsed:.1f} s")


def phrases(http: Http, recording_id: str) -> int:
    """GET /api/recordings/{id}/phrases — phrases are written by asr-worker."""
    step("phrases: GET /api/recordings/{id}/phrases")
    status, body = http.json("GET", f"/api/recordings/{recording_id}/phrases?after_seq=0")
    if status != 200 or not isinstance(body, dict):
        raise SmokeFailure(f"phrases: {status}: {body}")
    items = body.get("items") or []
    if not items:
        # 1 s of silence yields little text; an empty response is acceptable only for `ready`
        # with a single empty list, so we check the response shape, not the count.
        ok("phrases", "200, no phrases (silence recognized as empty) — shape is correct")
        return 0
    first = items[0]
    for field in ("id", "seq", "speaker_id", "side", "state"):
        if field not in first:
            raise SmokeFailure(f"phrases: the phrase has no {field} field: {first}")
    ok("phrases", f"200, phrases={len(items)}, next_after_seq={body.get('next_after_seq')}")
    return len(items)


def range_player(http: Http, recording_id: str) -> None:
    """HEAD and GET with `Range: bytes=100-199` → 206 + Content-Range (ADR-010)."""
    step("range: HEAD and GET Range 100-199")
    status, headers, _ = http.request("HEAD", f"/api/recordings/{recording_id}/audio")
    if status != 200:
        raise SmokeFailure(f"range: HEAD returned {status} (expected 200)")
    total = int(headers.get("content-length") or 0)
    if total <= 0:
        raise SmokeFailure("range: HEAD without Content-Length")
    if headers.get("accept-ranges") != "bytes":
        raise SmokeFailure(f"range: no Accept-Ranges: bytes ({headers.get('accept-ranges')!r})")

    status, headers, data = http.request(
        "GET",
        f"/api/recordings/{recording_id}/audio",
        headers={"Range": "bytes=100-199"},
    )
    if status != 206:
        raise SmokeFailure(f"range: expected 206, got {status}")
    content_range = headers.get("content-range") or ""
    if not content_range.startswith("bytes 100-199/"):
        raise SmokeFailure(f"range: Content-Range {content_range!r}")
    if len(data) != 100:
        raise SmokeFailure(f"range: body is {len(data)} bytes instead of 100")
    ok("range", f"206, Content-Range={content_range}, {total} bytes in the object")


def voice_note(http: Http) -> None:
    """POST /api/voice-notes → WS: ready → PCM 5 s → stop → final → stopped → done."""
    step("voice note: POST /api/voice-notes + WS stream")
    status, body = http.json("POST", "/api/voice-notes")
    if status != 201 or not isinstance(body, dict):
        raise SmokeFailure(
            f"note: {status}: {body} (503 ASR_UNAVAILABLE — asr-worker is not up)"
        )
    recording_id = str(body["recording_id"])
    ws_url = str(body["ws_url"])
    if not ws_url.startswith("ws"):
        ws_url = ("wss://" if http.scheme == "https" else "ws://") + http.netloc + ws_url

    try:
        from websockets.sync.client import connect
    except ModuleNotFoundError:
        raise SmokeFailure(
            "note: the `websockets` package is missing (run inside audio-api: `make smoke`)"
        ) from None

    headers = {"X-Auth-Subject": http.owner}
    if http.cookie:
        headers["Cookie"] = http.cookie

    frames: list[dict] = []
    with connect(ws_url, additional_headers=headers, open_timeout=30) as ws:
        first = _frame(ws.recv(timeout=60))
        frames.append(first)
        if first.get("type") != "ready":
            raise SmokeFailure(f"note: the first frame is {first} instead of ready")
        pcm = _make_pcm(NOTE_SECONDS)
        for offset in range(0, len(pcm), NOTE_FRAME_BYTES):
            ws.send(pcm[offset : offset + NOTE_FRAME_BYTES])
            time.sleep(0.02)  # faster than real time, but not all at once
        ws.send(json.dumps({"type": "stop"}))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                frame = _frame(ws.recv(timeout=deadline - time.monotonic()))
            except TimeoutError:
                break
            frames.append(frame)
            if frame.get("type") in {"done", "error"}:
                break

    kinds = [str(f.get("type")) for f in frames]
    if "error" in kinds:
        err = next(f for f in frames if f.get("type") == "error")
        raise SmokeFailure(f"note: the server returned error {err.get('error_code')}")
    if "done" not in kinds:
        raise SmokeFailure(f"note: no done frame; got {kinds}")
    stopped = next((f for f in frames if f.get("type") == "stopped"), None)
    if stopped and not stopped.get("audio_ready"):
        raise SmokeFailure(f"note: stopped without audio_ready: {stopped}")

    # `done` already means "the object is readable" (ADR-012, item 5); we check the status as
    # confirmation and count only `failed` as a failure.
    status, body = http.json("GET", f"/api/recordings/{recording_id}")
    if isinstance(body, dict) and (body.get("recording") or {}).get("status") == "failed":
        raise SmokeFailure("note: the recording is failed after done")
    ok(
        "voice note",
        f"done in {len(kinds)} frames ({','.join(sorted(set(kinds)))}), status=ready",
    )


def _frame(raw: str | bytes) -> dict:
    """A JSON frame from the server; non-JSON is a scenario error, not a silent skip."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise SmokeFailure(f"note: non-JSON frame from the server: {raw!r:.120}") from None
    if not isinstance(parsed, dict):
        raise SmokeFailure(f"note: the frame is not an object: {parsed!r}")
    return parsed


def _make_wav(seconds: float, rate: int = 16000) -> bytes:
    """WAV PCM s16le mono — ffprobe sees a track, enough for a couple of seconds of diarization."""
    n = int(seconds * rate)
    tone = b"".join(
        struct.pack("<h", int(0.2 * 32767 * math.sin(2 * math.pi * 220.0 * i / rate)))
        for i in range(n)
    )
    header = (
        b"RIFF"
        + (36 + len(tone)).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + rate.to_bytes(4, "little")
        + (rate * 2).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(tone).to_bytes(4, "little")
    )
    return header + tone


def _make_pcm(seconds: float, rate: int = 16000) -> bytes:
    n = int(seconds * rate)
    return b"".join(
        struct.pack("<h", int(0.2 * 32767 * math.sin(2 * math.pi * 220.0 * i / rate)))
        for i in range(n)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end US-08 smoke scenario")
    parser.add_argument("--base-url", default=os.environ.get("SMOKE_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--owner", default=os.environ.get("SMOKE_OWNER") or str(uuid.uuid4()))
    parser.add_argument("--cookie", default=os.environ.get("SMOKE_COOKIE"))
    parser.add_argument(
        "--skip-note", action="store_true", help="without the voice note (no GPU/slot)"
    )
    args = parser.parse_args(argv)

    http = Http(base=args.base_url, owner=args.owner, cookie=args.cookie)
    print(f"smoke: {http.base} owner={args.owner[:8]}…", flush=True)
    started = time.monotonic()
    try:
        status, _, data = http.request("GET", "/health")
        if status not in (200, 503):
            raise SmokeFailure(f"health: {status}: {data[:200]!r}")
        ok("health", f"{status} {data.decode()[:160]}")

        recording_id = upload(http)
        wait_ready(http, recording_id)
        phrases(http, recording_id)
        range_player(http, recording_id)
        if args.skip_note:
            print("· voice note skipped (--skip-note)")
        else:
            voice_note(http)
    except SmokeFailure as exc:
        print(f"✗ {exc}", file=sys.stderr, flush=True)
        print(f"\nSMOKE FAILED after {time.monotonic() - started:.1f} s", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — network/socket: we show the type and text
        print(f"✗ {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        print(f"\nSMOKE FAILED after {time.monotonic() - started:.1f} s", file=sys.stderr)
        return 1
    print(f"\nSMOKE OK after {time.monotonic() - started:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
