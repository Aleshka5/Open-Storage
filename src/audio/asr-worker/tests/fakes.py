"""Port fakes for the asr-worker tests (no GPU, no containers)."""

from __future__ import annotations

from typing import Any

from app.application.ports.asr_model import AsrModel
from app.application.ports.gpu_lease import LeaseDenied
from app.domain.transcription import Phrase, TranscriptionOutput


class FakeObjectStore:
    """In-memory object: read_window slices a range out of the normalized WAV.

    For tests a window is simply a byte slice of the object; the WAV header (44 bytes) is
    not accounted for in tests, because `window_byte_range` counts from the data chunk.
    To keep it simple we store a "raw" slice (no header) and read_window slices it as is.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads: list[tuple[str, int, int]] = []

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def exists(self, key: str) -> bool:
        return key in self.objects

    def read_window(self, key: str, *, start_byte: int, num_bytes: int) -> bytes:
        self.reads.append((key, start_byte, num_bytes))
        data = self.objects.get(key, b"")
        return data[start_byte : start_byte + num_bytes]


class FakePhraseRepo:
    def __init__(self) -> None:
        self.phrases: dict[tuple[str, int], dict[str, Any]] = {}
        self.speakers: dict[tuple[str, str], str] = {}  # (recording, key) -> _id
        self.upserts: list[Phrase] = []

    def add_speaker(self, recording_id: str, speaker_key: str, speaker_id: str) -> None:
        self.speakers[(recording_id, speaker_key)] = speaker_id

    def upsert(self, owner_id: str, recording_id: str, phrase: Phrase) -> None:
        self.upserts.append(phrase)
        key = (recording_id, phrase.seq)
        if key not in self.phrases:
            self.phrases[key] = {
                "_id": f"id-{phrase.seq}",
                "owner_user_id": owner_id,
                "recording_id": recording_id,
                "seq": phrase.seq,
                "speaker_id": phrase.speaker_id,
                "text": phrase.text,
                "start_ms": phrase.start_ms,
                "end_ms": phrase.end_ms,
                "state": "final",
                "side": "left",
                "overlap": phrase.overlap,
                "revision": 0,
                "created_at": "2026-11-01T09:00:00Z",
                "updated_at": "2026-11-01T09:00:00Z",
            }
        else:
            doc = self.phrases[key]
            doc["text"] = phrase.text
            doc["speaker_id"] = phrase.speaker_id
            doc["end_ms"] = phrase.end_ms
            doc["updated_at"] = "2026-11-01T09:00:01Z"

    def speaker_id_for(self, owner_id: str, recording_id: str, speaker_key: str) -> str | None:
        return self.speakers.get((recording_id, speaker_key))


class FakeQueue:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.dead: list[tuple[str, dict[str, Any]]] = []
        self.available = True

    def declare(self, queue: str) -> None:
        pass

    def publish(self, queue, body, *, message_id=None, correlation_id=None) -> None:
        self.published.append(
            (queue, body, {"message_id": message_id, "correlation_id": correlation_id})
        )

    def publish_dead(self, queue: str, body: dict[str, Any]) -> None:
        self.dead.append((queue, body))

    def consume(self, queue):
        return iter(())

    def ack(self, delivery_tag):
        pass

    def nack(self, delivery_tag, *, requeue=False):
        pass

    def is_available(self):
        return self.available

    def close(self):
        pass

    def events(self) -> list[dict[str, Any]]:
        return [b for q, b, _ in self.published if q == "audio.events"]


class FakeGpuLease:
    def __init__(self) -> None:
        self.deny = False
        self.acquired: list[str] = []
        self.released: int = 0
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self, klass: str) -> None:
        if self.deny:
            raise LeaseDenied("gpu busy")
        self._held = True
        self.acquired.append(klass)

    def heartbeat(self) -> None:
        pass

    def release(self) -> None:
        if self._held:
            self.released += 1
            self._held = False


def fake_model(texts=None, language: str | None = "ru") -> AsrModel:
    """Synthetic model: fixed text per seq + the model language."""

    class _Model:
        loaded = True

        def load(self) -> None:
            self.loaded = True

        def transcribe_windows(self, windows, *, seqs, language_hint=None) -> TranscriptionOutput:
            # Text per seq: from `texts` (dict seq->text) or the default.
            out = {}
            for seq in seqs:
                if texts is not None:
                    out[seq] = texts.get(seq, "text")
                else:
                    out[seq] = f"phrase-{seq}"
            return TranscriptionOutput(texts=out, language=language)

    return _Model()


def oom_model() -> AsrModel:
    """A model that raises CUDA OOM on any batch of more than 1 window."""

    class _Model:
        loaded = True
        calls: int = 0

        def load(self) -> None:
            pass

        def transcribe_windows(self, windows, *, seqs, language_hint=None) -> TranscriptionOutput:
            self.calls += 1
            if len(windows) > 1:
                raise RuntimeError("CUDA out of memory")
            return TranscriptionOutput(
                texts={seqs[0]: "ok"}, language="ru"
            )

    return _Model()


class StreamFakeModel:
    """StreamModel fake: the text grows with the call count, revision is tracked outside."""

    def __init__(self, texts=None):
        self._texts = list(texts or ["hello", "hello world"])
        self.calls = 0

    def transcribe_pcm(self, pcm: bytes):
        self.calls += 1
        idx = min(self.calls - 1, len(self._texts) - 1)
        return self._texts[idx], "ru"


class StreamFakeRepo:
    """PhraseRepo fake for open-frame validation + stream persistence."""

    def __init__(self, *, phrase_side="right", speaker_is_me=True, recording_exists=True,
                 phrase_exists=True):
        self.phrase_side = phrase_side
        self.speaker_is_me_flag = speaker_is_me
        self.recording_exists = recording_exists
        self.phrase_exists = phrase_exists
        self.updated = []

    def get_recording(self, recording_id: str, owner_id: str):
        if self.recording_exists:
            return {"_id": recording_id}
        return None

    def get_note_phrase(self, recording_id, owner_id, phrase_id):
        if self.phrase_exists:
            return {"_id": phrase_id, "speaker_id": "sp1", "side": self.phrase_side}
        return None

    def speaker_is_me(self, recording_id, owner_id, speaker_id):
        return self.speaker_is_me_flag

    def update_stream_phrase(self, recording_id, owner_id, phrase_id, *, text,
                             end_ms, state, revision):
        self.updated.append({"text": text, "end_ms": end_ms, "state": state,
                             "revision": revision})
