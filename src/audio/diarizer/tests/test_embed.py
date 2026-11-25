"""UC-D2 tests: the note voice embedding via `audio.embedding`.

us-07/init.md criteria the worker holds:
- after processing `voice_embedding` is non-empty, dimension = the collection's;
- a note shorter than 1 s → `embedding.failed (too_short)`, `.dead`, no vector written;
- a foreign object is not read; a missing one — `.dead (object_not_found)`;
- dimension ≠ collection's → the vector is written, the event carries `dim_mismatch: true`;
- GPU busy → `.retry` (`nack_retry`) without bumping `attempt`, lease class `interactive`;
- a redelivery overwrites the vector instead of creating a second one.
"""

from __future__ import annotations

from app.application.embed import ACK, DEAD, NACK_RETRY, EmbeddingHandler
from app.domain.diarization import CENTROID_DIM
from tests.embed_helpers import JOB, make_embedding_message, note_key
from tests.fakes import FakeEmbeddingModel, FakeRecordingRepo

OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
OTHER_OWNER = "11111111-2222-3333-4444-555555555555"
RECORDING = "8a7b6c5d-4e3f-4a2b-9c1d-0e1f2a3b4c5d"


class _Normalizer:
    """Normalization fake: copies bytes, the duration is set by the test."""

    def __init__(self, duration_ms: int = 4200) -> None:
        self.duration_ms = duration_ms
        self.fail = False
        self.normalized: list[tuple[str, str]] = []

    def normalize(self, src_path: str, dst_path: str) -> None:
        if self.fail:
            from app.application.ports.audio_normalizer import NormalizeError

            raise NormalizeError("decode")
        from pathlib import Path

        self.normalized.append((src_path, dst_path))
        Path(dst_path).write_bytes(Path(src_path).read_bytes())

    def probe_duration_ms(self, path: str) -> int | None:
        return self.duration_ms


def _handler(
    settings,
    *,
    store,
    queue,
    lease,
    recording_repo,
    model=None,
    normalizer=None,
) -> EmbeddingHandler:
    return EmbeddingHandler(
        settings=settings,
        model=model or FakeEmbeddingModel(),
        store=store,
        repo=recording_repo,
        queue=queue,
        normalizer=normalizer or _Normalizer(),
        lease=lease,
    )


def _seed_note(store, repo, *, owner=OWNER, recording=RECORDING, key=None):
    key = key or note_key(owner, recording)
    store.put(key, b"webm-bytes")
    repo.seed(recording, owner, kind="voice_note", voice_embedding=None)
    return key


def test_embedding_written_ready_event(settings, store, queue, lease, recording_repo):
    key = _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    action = handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING))

    assert action == ACK
    doc = recording_repo.docs[RECORDING]
    assert len(doc["voice_embedding"]) == CENTROID_DIM
    assert doc["voice_embedding_model"] == "pyannote/embedding@test-rev"
    events = queue.published_embedding_events()
    assert [e["event"] for e in events] == ["embedding.completed"]
    data = events[0]["data"]
    assert data["dim"] == CENTROID_DIM
    assert data["dim_mismatch"] is False
    # Lease class is interactive (above diarization), released after the inference.
    assert lease.acquired == ["interactive"]
    assert lease.held is False
    assert store.downloaded == [key]


def test_too_short_note_no_vector_dead(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings,
        store=store,
        queue=queue,
        lease=lease,
        recording_repo=recording_repo,
        normalizer=_Normalizer(duration_ms=900),
    )
    action = handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING))

    assert action == DEAD
    assert recording_repo.docs[RECORDING]["voice_embedding"] is None
    events = queue.published_embedding_events()
    assert [e["event"] for e in events] == ["embedding.failed"]
    assert events[0]["data"]["error_code"] == "too_short"
    # The GPU was not taken for 0.9 s; the message went to `.dead`, not to an endless `.retry`.
    assert lease.acquired == []
    assert queue.dead and queue.dead[0][0] == "audio.embedding"


def test_exactly_one_second_is_enough(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings,
        store=store,
        queue=queue,
        lease=lease,
        recording_repo=recording_repo,
        normalizer=_Normalizer(duration_ms=1000),
    )
    assert handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING)) == ACK
    assert recording_repo.docs[RECORDING]["voice_embedding"] is not None


def test_foreign_key_not_read(settings, store, queue, lease, recording_repo):
    # The object belongs to another owner — not read, no retry paid.
    _seed_note(store, repo=recording_repo, owner=OTHER_OWNER, recording=RECORDING)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    msg = make_embedding_message(owner=OWNER, recording=RECORDING)
    msg["audio_key"] = note_key(OTHER_OWNER, RECORDING)
    assert handler.handle(msg) == DEAD
    assert store.downloaded == []
    assert queue.published_embedding_events() == []


def test_object_not_found_dead(settings, store, queue, lease, recording_repo):
    recording_repo.seed(RECORDING, OWNER, voice_embedding=None)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    assert handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING)) == DEAD
    events = queue.published_embedding_events()
    assert events[0]["data"]["error_code"] == "object_not_found"
    assert recording_repo.docs[RECORDING]["voice_embedding"] is None


def test_dim_mismatch_written_with_flag(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings,
        store=store,
        queue=queue,
        lease=lease,
        recording_repo=recording_repo,
        model=FakeEmbeddingModel(dim=192),
    )
    assert handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING)) == ACK
    # The vector is written (contract: "the embedding is written"), the flag lives in the event.
    assert len(recording_repo.docs[RECORDING]["voice_embedding"]) == 192
    events = queue.published_embedding_events()
    assert events[0]["data"]["dim_mismatch"] is True
    assert events[0]["data"]["dim"] == 192


def test_gpu_busy_retries_without_attempt_growth(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    lease.deny = True
    model = FakeEmbeddingModel()
    handler = _handler(
        settings,
        store=store,
        queue=queue,
        lease=lease,
        recording_repo=recording_repo,
        model=model,
    )
    msg = make_embedding_message(owner=OWNER, recording=RECORDING)
    assert handler.handle(msg) == NACK_RETRY
    assert msg["attempt"] == 0
    assert model.calls == []
    assert recording_repo.docs[RECORDING]["voice_embedding"] is None


def test_redelivery_overwrites_single_vector(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    msg = make_embedding_message(owner=OWNER, recording=RECORDING)
    assert handler.handle(dict(msg)) == ACK
    first = list(recording_repo.docs[RECORDING]["voice_embedding"])
    assert handler.handle(dict(msg)) == ACK
    # The field holds a single value; a second vector does not "extend" it.
    assert recording_repo.docs[RECORDING]["voice_embedding"] == first
    assert len(lease.acquired) == 2


def test_decode_failure_dead(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    normalizer = _Normalizer()
    normalizer.fail = True
    handler = _handler(
        settings,
        store=store,
        queue=queue,
        lease=lease,
        recording_repo=recording_repo,
        normalizer=normalizer,
    )
    assert handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING)) == DEAD
    assert queue.published_embedding_events()[0]["data"]["error_code"] == "failed_media"


def test_scratch_cleaned(settings, store, queue, lease, recording_repo, tmp_path):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING))
    assert not (tmp_path / "audio" / JOB).exists()


def test_other_owner_recording_document_untouched(
    settings, store, queue, lease
):
    """`$set` with an owner filter: a foreign recording document is unchanged."""
    repo = FakeRecordingRepo()
    other_key = note_key(OWNER, RECORDING)
    store.put(other_key, b"webm-bytes")
    # The document exists but belongs to another owner.
    repo.seed(RECORDING, OTHER_OWNER, voice_embedding=None)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=repo
    )
    handler.handle(make_embedding_message(owner=OWNER, recording=RECORDING))
    assert repo.docs[RECORDING]["voice_embedding"] is None


def test_schema_version_99_dead(settings, store, queue, lease, recording_repo):
    _seed_note(store, repo=recording_repo)
    handler = _handler(
        settings, store=store, queue=queue, lease=lease, recording_repo=recording_repo
    )
    msg = make_embedding_message(owner=OWNER, recording=RECORDING, schema_version=99)
    assert handler.handle(msg) == DEAD
    assert store.downloaded == []
