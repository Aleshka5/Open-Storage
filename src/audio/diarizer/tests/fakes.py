"""Port fakes for the diarizer tests (no GPU, no containers)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.application.ports.audio_normalizer import NormalizeError
from app.application.ports.diarizer_model import DiarizerModel
from app.application.ports.gpu_lease import LeaseDenied
from app.domain.diarization import (
    CENTROID_DIM,
    DiarizationResult,
    SpeakerSpec,
    Turn,
    build_speakers,
)


class FakeObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.meta: dict[str, dict[str, Any]] = {}
        self.downloaded: list[str] = []

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = data
        self.meta[key] = {"content_type": content_type, "size": len(data)}

    def download(self, key: str, dest_path: str) -> None:
        if key not in self.objects:
            raise KeyError(key)
        self.downloaded.append(key)
        Path(dest_path).write_bytes(self.objects[key])

    def upload_file(self, key: str, src_path: str, content_type: str) -> None:
        data = Path(src_path).read_bytes()
        self.objects[key] = data
        self.meta[key] = {"content_type": content_type, "size": len(data)}

    def exists(self, key: str) -> bool:
        return key in self.objects


class FakeNormalizer:
    def __init__(self) -> None:
        self.fail = False
        self.normalized: list[tuple[str, str]] = []

    def normalize(self, src_path: str, dst_path: str) -> None:
        if self.fail:
            raise NormalizeError("ffmpeg failed to decode the source")
        self.normalized.append((src_path, dst_path))
        # Copy the source as "16 kHz mono s16le" — in tests this is a synthetic WAV.
        Path(dst_path).write_bytes(Path(src_path).read_bytes())

    def probe_duration_ms(self, path: str) -> int | None:
        return 16000


class FakeRecordingRepo:
    """`recordings` as seen by diarizer: the only fields are the voice vectors."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def seed(self, recording_id: str, owner_id: str, **fields: Any) -> None:
        self.docs[recording_id] = {
            "_id": recording_id,
            "owner_user_id": owner_id,
            **fields,
        }

    def set_voice_embedding(
        self, owner_id: str, recording_id: str, *, embedding: list[float], model: str
    ) -> bool:
        doc = self.docs.get(recording_id)
        if doc is None or doc["owner_user_id"] != owner_id:
            return False
        doc["voice_embedding"] = list(embedding)
        doc["voice_embedding_model"] = model
        return True


class FakeEmbeddingModel:
    """One vector per file: `dim`-dimensional, normalized, deterministic."""

    def __init__(self, dim: int = CENTROID_DIM, *, fail: str | None = None) -> None:
        self.dim = dim
        self.fail = fail
        self.calls: list[str] = []
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def model_id(self) -> str:
        return "pyannote/embedding@test-rev"

    def embed(self, wav_path: str) -> list[float]:
        self.calls.append(wav_path)
        if self.fail == "oom":
            raise RuntimeError("CUDA out of memory")
        if self.fail:
            raise RuntimeError(self.fail)
        vec = [1.0 / (i + 1) for i in range(self.dim)]
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm for v in vec]


class FakeSpeakerRepo:
    def __init__(self) -> None:
        self.speakers: dict[tuple[str, str], dict[str, Any]] = {}
        self.upserts: list[SpeakerSpec] = []

    def upsert(self, owner_id: str, recording_id: str, spec: SpeakerSpec) -> None:
        self.upserts.append(spec)
        key = (recording_id, spec.speaker_key)
        if key not in self.speakers:
            self.speakers[key] = {
                "_id": f"id-{spec.speaker_key}",
                "owner_user_id": owner_id,
                "recording_id": recording_id,
                "speaker_key": spec.speaker_key,
                "order_index": spec.order_index,
                "centroid": list(spec.centroid),
                "label": f"Speaker {spec.order_index}",
                "nick_id": None,
                "is_me": False,
                "created_at": "2026-11-01T09:00:00Z",
                "updated_at": "2026-11-01T09:00:00Z",
            }
        else:
            # $set: centroid/order_index are updated; label/nick_id/is_me are not touched.
            doc = self.speakers[key]
            doc["centroid"] = list(spec.centroid)
            doc["order_index"] = spec.order_index
            doc["updated_at"] = "2026-11-01T09:00:01Z"


class FakeQueue:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.dead: list[tuple[str, dict[str, Any]]] = []
        self.available = True

    def publish_dead(self, queue: str, body: dict[str, Any]) -> None:
        """`<queue>.dead` directly: a nack would return the message to `.retry` forever."""
        self.dead.append((queue, body))

    def published_embedding_events(self) -> list[dict[str, Any]]:
        return [
            b
            for q, b, _ in self.published
            if q == "audio.events" and str(b.get("event", "")).startswith("embedding.")
        ]

    def declare(self, queue: str) -> None:
        pass

    def publish(self, queue, body, *, message_id=None, correlation_id=None) -> None:
        self.published.append(
            (queue, body, {"message_id": message_id, "correlation_id": correlation_id})
        )

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

    def published_events(self) -> list[dict[str, Any]]:
        return [b for q, b, _ in self.published if q == "audio.events"]

    def published_transcription(self) -> list[dict[str, Any]]:
        return [b for q, b, _ in self.published if q == "audio.transcription"]


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


def two_speaker_model(
    turns: list[Turn] | None = None, *, speakers: list[SpeakerSpec] | None = None
) -> DiarizerModel:
    """Synthetic model returning a known result (no inference)."""

    class _Model:
        loaded = True

        def load(self) -> None:
            self.loaded = True

        def diarize(self, wav_path: str) -> DiarizationResult:
            result_turns = turns or _default_turns()
            result_speakers = speakers or _default_speakers(result_turns)
            return DiarizationResult(
                turns=result_turns,
                speakers=result_speakers,
                duration_ms=max(t.end_ms for t in result_turns),
            )

    return _Model()


def _default_turns() -> list[Turn]:
    # Speaker 0 talks first (0..3.52s), then 1 (3.52..8.14s overlap), then 0 again.
    return [
        Turn(speaker_key="SPEAKER_00", start_ms=0, end_ms=3520, overlap=False),
        Turn(speaker_key="SPEAKER_01", start_ms=3520, end_ms=8140, overlap=True),
        Turn(speaker_key="SPEAKER_00", start_ms=8140, end_ms=12960, overlap=False),
    ]


def _default_speakers(turns: list[Turn]) -> list[SpeakerSpec]:
    centroids = {k: [0.0] * CENTROID_DIM for k in {t.speaker_key for t in turns}}
    return build_speakers(turns, centroids=centroids)
