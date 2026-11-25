"""Fake ports for scenario tests (no containers)."""

from __future__ import annotations

import base64
from typing import Any


class FakeRecordingRepo:
    """In-memory repository repeating the ownership and index semantics."""

    def __init__(self) -> None:
        self._recordings: dict[str, dict[str, Any]] = {}
        self._by_owner: dict[str, list[str]] = {}
        self.stall_candidates: set[str] = set()
        self._counters: dict[str, int] = {}

    async def insert_recording(self, recording: Any) -> None:
        doc = {
            "_id": recording.recording_id,
            "owner_user_id": recording.owner_user_id,
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
            "processing": recording.default_processing(),
            "created_at": recording.created_at,
            "updated_at": recording.created_at,
            "ready_at": None,
        }
        self._recordings[recording.recording_id] = doc
        self._by_owner.setdefault(recording.owner_user_id, []).append(recording.recording_id)

    async def get_recording(self, recording_id: str, owner_id: str) -> dict[str, Any] | None:
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return None
        return dict(doc)

    def get_recording_sync(self, recording_id: str, owner_id: str) -> dict[str, Any] | None:
        """Synchronous access for tests outside the event loop."""
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return None
        return dict(doc)

    async def list_recordings(
        self, owner_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        ids = self._by_owner.get(owner_id, [])
        docs = [dict(self._recordings[i]) for i in ids]
        docs.sort(key=lambda d: d["created_at"], reverse=True)
        if cursor:
            created = _decode_cursor(cursor)
            docs = [d for d in docs if d["created_at"] < created]
        has_more = len(docs) > limit
        docs = docs[:limit]
        nxt = _encode_cursor(docs[-1]["created_at"]) if has_more and docs else None
        return docs, nxt

    async def update_title(self, recording_id: str, owner_id: str, title: str) -> bool:
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return False
        doc["title"] = title
        return True

    async def set_status(self, recording_id, owner_id, *, status, error_code, **kw) -> bool:
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return False
        doc["status"] = status
        if "phrases_done" in kw and kw["phrases_done"] is not None:
            doc.setdefault("processing", {})["phrases_done"] = kw["phrases_done"]
        if "phrases_total" in kw and kw["phrases_total"] is not None:
            doc.setdefault("processing", {})["phrases_total"] = kw["phrases_total"]
        if kw.get("language") is not None:
            doc["language"] = kw["language"]
        if kw.get("ready_at") is not None:
            doc["ready_at"] = kw["ready_at"]
        doc.setdefault("processing", {})["error_code"] = error_code
        return True

    async def find_stalled(self, statuses, stall_seconds):
        # The fake returns recordings in diarizing/transcribing — for the watchdog unit test
        # we control that with the `stall_candidates` flag.
        out = []
        for rid, doc in self._recordings.items():
            if doc["status"] in statuses and rid in self.stall_candidates:
                out.append(dict(doc))
        return out

    async def mark_stalled(self, recording_id, owner_id):
        doc = self._recordings.get(recording_id)
        if doc is not None and doc["owner_user_id"] == owner_id:
            doc["status"] = "failed"
            doc.setdefault("processing", {})["error_code"] = "stalled"


    async def set_embedding(self, recording_id, owner_id, state) -> bool:
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return False
        doc.setdefault("processing", {})["embedding"] = state
        return True

    async def set_default_voice(self, recording_id, owner_id, *, is_default) -> None:
        doc = self._recordings.get(recording_id)
        if doc is not None and doc["owner_user_id"] == owner_id:
            doc["is_default_voice"] = is_default

    async def clear_default_voice(self, owner_id, *, keep_id) -> None:
        for rid, doc in self._recordings.items():
            if doc["owner_user_id"] == owner_id and doc.get("is_default_voice"):
                if keep_id is None or rid != keep_id:
                    doc["is_default_voice"] = False

    async def next_note_counter(self, owner_id) -> int:
        # Atomic in-memory increment: monotonic, never reused.
        key = f"voice_note_seq:{owner_id}"
        val = self._counters.get(key, 0) + 1
        self._counters[key] = val
        return val

    async def finalize_note(
        self, recording_id, owner_id, *, duration_ms, audio_bytes, language, has_text
    ) -> bool:
        doc = self._recordings.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return False
        doc["duration_ms"] = duration_ms
        doc["audio_bytes"] = audio_bytes
        doc["audio_content_type"] = "audio/webm"
        if language is not None:
            doc["language"] = language
        if has_text:
            doc["status"] = "ready"
            doc["ready_at"] = "2026-11-01T10:00:00Z"
            doc.setdefault("processing", {})["phrases_done"] = 1
            doc.setdefault("processing", {})["phrases_total"] = 1
        else:
            doc["status"] = "failed"
            doc.setdefault("processing", {})["error_code"] = "nospeech"
        return True


def _encode_cursor(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def _decode_cursor(c: str) -> str:
    padding = "=" * (-len(c) % 4)
    return base64.urlsafe_b64decode(c + padding).decode()


class FakeAudioStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.meta: dict[str, dict[str, Any]] = {}
        self.fail_put = False
        self.available = True
        self.multipart_uploads: dict[str, dict[str, Any]] = {}
        self.aborted: list[str] = []

    async def put_object_stream(
        self, key, content_type, stream, *, size_hint=None, owner_id=None, recording_id=None
    ) -> None:
        if self.fail_put:
            raise RuntimeError("storage down")
        if hasattr(stream, "read"):
            data = stream.read()
        else:
            data = b"".join(stream)
        self.objects[key] = data
        self.meta[key] = {
            "content_type": content_type,
            "size": len(data),
            "owner": owner_id,
            "recording": recording_id,
        }

    async def check(self) -> bool:
        return self.available

    async def stat_object(self, key: str) -> dict | None:
        if key in self.meta:
            return self.meta[key]
        return None

    async def create_multipart(self, key: str, content_type: str) -> str:
        self.multipart_uploads[key] = {
            "content_type": content_type,
            "upload_id": f"up-{len(self.multipart_uploads)}",
            "parts": [],
        }
        return self.multipart_uploads[key]["upload_id"]

    async def upload_part(self, key, upload_id, part_number, data):
        up = self.multipart_uploads[key]
        up["parts"].append((part_number, bytes(data)))
        return f'etag-{part_number}'

    async def complete_multipart(self, key, upload_id, parts):
        up = self.multipart_uploads[key]
        self.objects[key] = b"".join(d for _, d in sorted(up["parts"]))
        self.meta[key] = {"content_type": up["content_type"], "size": len(self.objects[key])}
        self.multipart_uploads.pop(key, None)

    async def abort_multipart(self, key, upload_id):
        self.aborted.append(key)
        self.multipart_uploads.pop(key, None)

    async def get_object_range(self, key, *, start=0, length=None):
        data = self.objects.get(key, b"")
        total = len(data)
        if length is None:
            return data[start:], total
        return data[start : start + length], total


class FakePcmMuxer:
    """Muxer fake: the "container" = a marker + reversed PCM, so that it is visible that raw PCM
    is not what goes into the object (D1).

    `raise_unavailable` — ffmpeg is not in the image; `fail_after` — ffmpeg fails after N
    writes (`MuxerError`).
    """

    MAGIC = b"\x1a\x45\xdf\xa3"  # EBML/WebM magic, as in a real container

    def __init__(self, *, raise_unavailable=False, fail_after=None) -> None:
        self.raise_unavailable = raise_unavailable
        self.fail_after = fail_after
        self.started = False
        self.finished = False
        self.aborted = False
        self.writes: list[bytes] = []
        self._parts: list[bytes] = []

    async def start(self) -> None:
        if self.raise_unavailable:
            from app.infrastructure.pcm_muxer import MuxerUnavailable

            raise MuxerUnavailable("no ffmpeg")
        self.started = True

    async def write(self, pcm: bytes) -> bytes:
        from app.infrastructure.pcm_muxer import MuxerError

        if not self.started or self.aborted or self.finished:
            raise MuxerError("muxer not running")
        if self.fail_after is not None and len(self.writes) >= self.fail_after:
            raise MuxerError("boom")
        self.writes.append(bytes(pcm))
        # XOR 0xFF: the bytes differ from PCM even for a zero signal (the "this is not PCM" marker).
        return bytes(b ^ 0xFF for b in pcm)

    async def finish(self) -> bytes:
        self.finished = True
        # The container gets the EBML magic only at the end (like Tracks in ffmpeg).
        return self.MAGIC + b"tail"

    async def abort(self) -> None:
        self.aborted = True


class FakeMuxerFactory:
    """Fake muxer factory: one instance per `connect`."""

    def __init__(self, **muxer_kwargs) -> None:
        self._kwargs = muxer_kwargs
        self.muxers: list[FakePcmMuxer] = []

    def __call__(self) -> FakePcmMuxer:
        m = FakePcmMuxer(**self._kwargs)
        self.muxers.append(m)
        return m

    @property
    def last(self) -> FakePcmMuxer | None:
        return self.muxers[-1] if self.muxers else None


class FakeQueue:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.available = True
        self.fail_publish = False

    def declare(self, queue: str) -> None:
        pass

    def publish(self, queue, body, *, message_id=None, correlation_id=None) -> None:
        if self.fail_publish:
            raise RuntimeError("broker down")
        self.published.append(
            (queue, body, {"message_id": message_id, "correlation_id": correlation_id})
        )

    def consume(self, queue: str):
        return iter(())

    def ack(self, delivery_tag):
        pass

    def nack(self, delivery_tag, *, requeue=False):
        pass

    def is_available(self):
        return self.available

    def close(self):
        pass


class FakeVoiceRepo:
    """In-memory voice repository (speakers/phrases/nicks) with ownership semantics."""

    def __init__(self) -> None:
        self.speakers: dict[str, dict[str, Any]] = {}
        self.phrases: dict[str, dict[str, Any]] = {}
        self.nicks: dict[str, dict[str, Any]] = {}
        self.owner_voices: dict[str, dict[str, Any]] = {}

    async def get_owner_voice(self, owner_id):
        doc = self.owner_voices.get(owner_id)
        return dict(doc) if doc is not None else None

    async def set_owner_voice(
        self, owner_id, *, recording_id, speaker_id, qdrant_point_id
    ):
        doc = {
            "_id": owner_id,
            "recording_id": recording_id,
            "speaker_id": speaker_id,
            "qdrant_point_id": qdrant_point_id,
            "updated_at": "2026-11-01T11:00:00Z",
        }
        self.owner_voices[owner_id] = doc
        return dict(doc)


    async def get_speaker(self, recording_id, speaker_id, owner_id):
        s = self.speakers.get(speaker_id)
        if (
            s is None
            or s["owner_user_id"] != owner_id
            or s["recording_id"] != recording_id
        ):
            return None
        return dict(s)


    async def get_nick_by_id(self, nick_id, owner_id):
        n = self.nicks.get(nick_id)
        if n is None or n["owner_user_id"] != owner_id:
            return None
        return dict(n)


    async def find_nick_by_name_key(self, owner_id, name_key):
        for n in self.nicks.values():
            if n["owner_user_id"] == owner_id and n["name_key"] == name_key:
                return dict(n)
        return None


    async def create_nick(self, nick):
        # We emulate unique (owner, name_key): a repeat returns the existing one.
        for n in self.nicks.values():
            if (
                n["owner_user_id"] == nick["owner_user_id"]
                and n["name_key"] == nick["name_key"]
            ):
                return dict(n)
        self.nicks[nick["_id"]] = dict(nick)
        return dict(nick)


    async def assign_speaker(
        self, recording_id, speaker_id, owner_id, *, label, nick_id, is_me
    ):
        s = self.speakers.get(speaker_id)
        if s is None or s["owner_user_id"] != owner_id:
            return False
        s["label"] = label
        s["nick_id"] = nick_id
        s["is_me"] = is_me
        return True


    async def set_phrases_side(self, recording_id, speaker_id, owner_id, *, side):
        n = 0
        for p in self.phrases.values():
            if (
                p["owner_user_id"] == owner_id
                and p["recording_id"] == recording_id
                and p["speaker_id"] == speaker_id
            ):
                p["side"] = side
                n += 1
        return n

    async def create_self_speaker(self, recording_id, owner_id, speaker_id):
        self.speakers[speaker_id] = {
            "_id": speaker_id,
            "owner_user_id": owner_id,
            "recording_id": recording_id,
            "speaker_key": "SELF",
            "order_index": 1,
            "centroid": None,
            "label": "Me",
            "nick_id": None,
            "is_me": True,
        }

    async def create_note_phrase(
        self, recording_id, owner_id, *, phrase_id, speaker_id
    ):
        self.phrases[phrase_id] = {
            "_id": phrase_id,
            "owner_user_id": owner_id,
            "recording_id": recording_id,
            "speaker_id": speaker_id,
            "seq": 1,
            "start_ms": 0,
            "end_ms": 0,
            "text": "",
            "side": "right",
            "state": "partial",
            "overlap": False,
            "revision": 0,
        }


    async def list_phrases(
        self, recording_id, owner_id, *, after_seq, limit
    ):
        # MongoVoiceRepo.list_phrases semantics: owner+recording, seq>after_seq,
        # sorted by seq ASC, label from speakers.label, side defaults to left.
        labels = {
            s["_id"]: s.get("label")
            for s in self.speakers.values()
            if s.get("owner_user_id") == owner_id
            and s.get("recording_id") == recording_id
        }
        matching = [
            p
            for p in self.phrases.values()
            if p.get("owner_user_id") == owner_id
            and p.get("recording_id") == recording_id
        ]
        matching = [p for p in matching if (p.get("seq") or 0) > after_seq]
        matching.sort(key=lambda p: p.get("seq") or 0)

        items = []
        next_after_seq = after_seq
        for p in matching[:limit]:
            seq = p.get("seq")
            speaker_id = p.get("speaker_id")
            items.append(
                {
                    "id": p.get("_id"),
                    "seq": seq,
                    "speaker_id": speaker_id,
                    "label": labels.get(speaker_id),
                    "side": p.get("side", "left"),
                    "start_ms": p.get("start_ms"),
                    "end_ms": p.get("end_ms"),
                    "text": p.get("text"),
                    "state": p.get("state", "final"),
                    "revision": p.get("revision", 0),
                    "overlap": p.get("overlap", False),
                }
            )
            next_after_seq = max(next_after_seq, seq or 0)
        return items, next_after_seq


class FakeVoiceIndex:
    """In-memory voice index: cosine search, upsert, "Me" points."""

    def __init__(self) -> None:
        self.points: dict[str, dict[str, Any]] = {}
        self.available = True
        self.incompatible = False
        self.created_sizes: list[int] = []
        self.upserted_points: list[str] = []
        self.deleted_points: list[str] = []

    async def ensure_collection(self, vector_size):
        self.created_sizes.append(vector_size)
        if self.incompatible:
            from app.application.ports.voice_index import VoiceIndexIncompatible

            raise VoiceIndexIncompatible(
                f"collection: size={vector_size + 1}, expected {vector_size}"
            )

    async def search(self, owner_id, vector, *, limit):
        if not self.available:
            from app.application.ports.voice_index import VoiceIndexUnavailable

            raise VoiceIndexUnavailable("index unavailable")
        scored = []
        for pid, p in self.points.items():
            if p["payload"].get("owner_user_id") != owner_id:
                continue
            score = _cosine(vector, p["vector"])
            scored.append((score, pid, p))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            _FakePoint(pid, score, payload)
            for score, pid, payload in scored[:limit]
        ]

    async def has_me(self, owner_id):
        if not self.available:
            from app.application.ports.voice_index import VoiceIndexUnavailable

            raise VoiceIndexUnavailable("index unavailable")
        return any(
            p["payload"].get("owner_user_id") == owner_id
            and p["payload"].get("kind") == "me"
            for p in self.points.values()
        )

    async def upsert_nick(self, owner_id, *, point_id, vector, payload):
        if not self.available:
            from app.application.ports.voice_index import VoiceIndexUnavailable

            raise VoiceIndexUnavailable("index unavailable")
        self.points[point_id] = {"vector": list(vector), "payload": dict(payload)}
        self.upserted_points.append(point_id)

    async def upsert_me(self, owner_id, *, point_id, vector, payload):
        if not self.available:
            from app.application.ports.voice_index import VoiceIndexUnavailable

            raise VoiceIndexUnavailable("index unavailable")
        self.points[point_id] = {"vector": list(vector), "payload": dict(payload)}
        self.upserted_points.append(point_id)

    async def delete_point(self, owner_id, *, point_id):
        if not self.available:
            from app.application.ports.voice_index import VoiceIndexUnavailable

            raise VoiceIndexUnavailable("index unavailable")
        self.deleted_points.append(point_id)
        point = self.points.get(point_id)
        # The real owner field name (not a made-up "OWNER"): the fake must read the same
        # payload that prod writes, otherwise it masks a bug in the filter (US-07 review, D4).
        if point is not None and point["payload"].get("owner_user_id") == owner_id:
            del self.points[point_id]


class _FakePoint:
    def __init__(self, point_id, score, payload):
        self.point_id = point_id
        self.score = score
        self.payload = payload


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FakeAsrStream:
    """Fake channel to asr-worker: a pre-set sequence of server frames."""

    def __init__(self, ready_on_open=True, server_frames=None, close_code=None):
        self.opened: dict = {}
        self.pcm_sent: list[bytes] = []
        self.stopped = False
        self.closed = False
        self._ready = ready_on_open
        # server_frames: a list of dict frames (~ partial/final/done/error) or a coroutine.
        self._frames = list(server_frames or [])
        self._close_code = close_code
        self.open_error = None

    async def open(self, *, recording_id, phrase_id, owner_id):
        self.opened = {"recording_id": recording_id, "phrase_id": phrase_id, "owner_id": owner_id}
        if self.open_error is not None:
            from app.application.ports.asr_stream import AsrStreamError

            raise AsrStreamError(self.open_error, "asr error")
        if not self._ready:
            self._close_code = 4503

    async def send_pcm(self, data: bytes) -> None:
        self.pcm_sent.append(data)

    async def send_stop(self) -> None:
        self.stopped = True

    async def recv(self):
        if self._frames:
            return dict(self._frames.pop(0))
        return None

    @property
    def close_code(self):
        return self._close_code

    async def close(self):
        self.closed = True


class FakeAsrFactory:
    """Fake stream factory: hands out pre-assembled FakeAsrStreams."""

    def __init__(self):
        self.streams: list[FakeAsrStream] = []

    def add(self, stream: FakeAsrStream) -> FakeAsrStream:
        self.streams.append(stream)
        return stream

    def connect(self, ws_url: str):
        return self.streams.pop(0)


class FakeAsrStatusFactory:
    """Fake factory whose /health returns the given (available, busy)."""

    def __init__(self, available=True, busy=False):
        self.available = available
        self.busy = busy
        self.streams: list[FakeAsrStream] = []

    def add(self, stream):
        self.streams.append(stream)
        return stream

    def connect(self, ws_url):
        return self.streams.pop(0)
