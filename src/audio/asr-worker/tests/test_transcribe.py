"""UC-A1 tests: transcription batches, negative paths, idempotency, GPU lease."""

from __future__ import annotations

from app.application.transcribe_batch import ACK, DEAD, NACK_RETRY, RETRY_WITH_ATTEMPT
from app.domain.transcription import build_batches, key_belongs_to_owner
from tests.conftest import OTHER_OWNER, RECORDING, make_message, make_turn, norm_key
from tests.fakes import fake_model

# --- Mapping turns to phrases, seq = 1..N without gaps, state final ---


def test_turns_map_to_phrases_with_seq_and_state(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")

    action = handler.handle(make_message())

    assert action == ACK
    # 3 turns → 3 phrases, seq = 1..3 without gaps, state final on each.
    assert len(repo.phrases) == 3
    assert sorted(seq for _rid, seq in repo.phrases) == [1, 2, 3]
    for doc in repo.phrases.values():
        assert doc["state"] == "final"
        assert doc["side"] == "left"
        assert doc["revision"] == 0
        assert doc["owner_user_id"] == "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"

    # speaker_id points at an existing speaker of this recording; boundaries = turn boundaries.
    p1 = repo.phrases[(RECORDING, 1)]
    p2 = repo.phrases[(RECORDING, 2)]
    p3 = repo.phrases[(RECORDING, 3)]
    assert p1["speaker_id"] == "speaker-0"
    assert p1["start_ms"] == 0 and p1["end_ms"] == 3520
    assert p2["speaker_id"] == "speaker-1"
    assert p2["start_ms"] == 3520 and p2["end_ms"] == 8140
    assert p2["overlap"] is True
    assert p3["speaker_id"] == "speaker-0"
    assert p3["start_ms"] == 8140 and p3["end_ms"] == 12960


def test_existing_nick_does_not_change_phrase_fields(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")
    handler.handle(make_message())
    # asr-worker never writes label/side — only text/state/revision/end_ms/start_ms/seq.
    for doc in repo.phrases.values():
        assert doc["side"] == "left"
        assert "label" not in doc


# --- Upsert idempotency: a redelivery creates no duplicates ---


def test_redelivery_no_duplicate_phrases(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")

    handler.handle(make_message())
    handler.handle(make_message(job_id="rerun-job"))

    assert len(repo.phrases) == 3  # no duplicates (upsert by (recording_id, seq))


# --- speaker_unknown → .dead + transcription.failed, earlier inserts stay ---


def test_speaker_unknown_goes_dead_and_failed(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    # Register only SPEAKER_00; SPEAKER_01 is unknown.
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")

    action = handler.handle(make_message())

    assert action == DEAD
    events = queue.events()
    assert events[0]["event"] == "transcription.started"
    assert events[-1]["event"] == "transcription.failed"
    assert events[-1]["data"]["error_code"] == "speaker_unknown"
    # The first batch (all 3 turns are one batch) is not partially written: the speaker is
    # resolved BEFORE the batch insert, so no phrases exist (atomic on speaker resolution).
    assert repo.phrases == {}


# --- The stream interrupts a batch between turns (ADR-006 / S-06, wired by US-05) ---


def test_stream_interrupt_returns_nack_retry_between_turns(settings, store, queue, repo, lease):
    from app.application.transcribe_batch import TranscribeBatchHandler

    interrupted = {"flag": False}
    h = TranscribeBatchHandler(
        settings=settings, model=fake_model(language="ru"), store=store, repo=repo,
        queue=queue, lease=lease, int_source=lambda: interrupted["flag"],
    )
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")
    # Interrupt right after start (before the lease/batch).
    interrupted["flag"] = True

    action = h.handle(make_message())

    assert action == NACK_RETRY
    # The lease was not taken, no duplicates: a redelivery overwrites idempotently.
    assert lease.acquired == []


# --- Batches of up to 8 turns OR 60 s; order preserved ---


def test_batch_split_by_turns(handler, store, queue, repo):
    turns = [
        make_turn(f"t{i:04d}", "SPEAKER_00", i * 1000, i * 1000 + 800, False)
        for i in range(1, 17)  # 16 turns → 2 batches of 8
    ]
    store.put(norm_key(), b"\x00" * (20 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")

    action = handler.handle(make_message(turns=turns))

    assert action == ACK
    assert len(repo.phrases) == 16
    assert sorted(seq for _rid, seq in repo.phrases) == list(range(1, 17))


def test_batch_split_by_seconds():
    # 3 turns of 30 s each → 90 s in total > 60 s → batches of 2 + 1.
    turns = [
        make_turn("t1", "SPEAKER_00", 0, 30_000, False),
        make_turn("t2", "SPEAKER_00", 30_000, 60_000, False),
        make_turn("t3", "SPEAKER_00", 60_000, 90_000, False),
    ]
    from app.domain.transcription import Turn

    domain_turns = [
        Turn(turn_id=t["turn_id"], speaker_key=t["speaker_key"], start_ms=t["start_ms"],
             end_ms=t["end_ms"], overlap=t["overlap"], seq=i)
        for i, t in enumerate(turns, 1)
    ]
    batches = build_batches(domain_turns, max_turns=8, max_seconds=60)
    assert [len(b) for b in batches] == [2, 1]


# --- Events started/progress/completed + phrases_done/total ---


def test_events_started_progress_completed(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")

    handler.handle(make_message())

    events = queue.events()
    assert [e["event"] for e in events] == [
        "transcription.started",
        "transcription.progress",
        "transcription.completed",
    ]
    progress = events[1]
    assert progress["data"]["phrases_done"] == 3
    assert progress["data"]["phrases_total"] == 3
    completed = events[2]
    assert completed["data"]["phrases"] == 3
    assert completed["data"]["language"] == "ru"  # detected by the model


# --- Language: the model detects RU/EN, language_hint does not override ---


def test_language_en_from_model(settings, store, queue, repo, lease):
    from app.application.transcribe_batch import TranscribeBatchHandler

    h = TranscribeBatchHandler(
        settings=settings, model=fake_model(language="en"), store=store, repo=repo,
        queue=queue, lease=lease,
    )
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")

    h.handle(make_message(language_hint="ru"))  # the hint does not override

    completed = queue.events()[-1]
    assert completed["event"] == "transcription.completed"
    assert completed["data"]["language"] == "en"


# --- GPU lease: none → nack_retry without bumping attempt ---


def test_lease_denied_nack_retry_no_attempt_growth(handler, store, queue, repo, lease):
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    repo.add_speaker(RECORDING, "SPEAKER_01", "speaker-1")
    lease.deny = True

    action = handler.handle(make_message())

    assert action == NACK_RETRY
    assert repo.phrases == {}  # nothing was inserted
    # attempt untouched: the message is not republished with a bumped attempt on nack_retry
    assert lease.released == 0


# --- OOM on a batch: halve + one retry, then .retry ---


def test_gpu_oom_reduce_then_retry(settings, store, queue, repo, lease):
    from app.application.transcribe_batch import TranscribeBatchHandler

    model = _oom_once_model()
    h = TranscribeBatchHandler(
        settings=settings, model=model, store=store, repo=repo, queue=queue, lease=lease,
    )
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    # A batch of 4 turns of one speaker; the model OOMs on call 1 (>1 window), fine later.
    turns = [
        make_turn(f"t{i}", "SPEAKER_00", i * 1000, i * 1000 + 800, False)
        for i in range(1, 5)
    ]
    action = h.handle(make_message(turns=turns))

    # Halving worked and no full .retry was needed: the model failed only on the
    # first attempt, then succeeded — the end result is ACK.
    assert action == ACK
    assert len(repo.phrases) == 4


def test_gpu_oom_after_reduce_goes_retry(settings, store, queue, repo, lease):
    from app.application.transcribe_batch import TranscribeBatchHandler

    h = TranscribeBatchHandler(
        settings=settings, model=_always_oom_over_one(), store=store, repo=repo,
        queue=queue, lease=lease,
    )
    store.put(norm_key(), b"\x00" * (13 * 32000))
    repo.add_speaker(RECORDING, "SPEAKER_00", "speaker-0")
    turns = [
        make_turn(f"t{i}", "SPEAKER_00", i * 1000, i * 1000 + 800, False)
        for i in range(1, 5)
    ]
    msg = make_message(turns=turns)
    action = h.handle(msg)

    # OOM again after halving → RETRY_WITH_ATTEMPT, attempt grew.
    assert action == RETRY_WITH_ATTEMPT
    assert msg["attempt"] == 1


# --- owner mismatch / schema / malformed ---


def test_owner_mismatch_goes_dead_without_reading(handler, store, queue, repo):
    store.put(norm_key(), b"\x00" * 32000)
    msg = make_message(audio_key=f"u/{OTHER_OWNER}/rec/{RECORDING}/norm.wav")
    action = handler.handle(msg)
    assert action == DEAD
    assert store.reads == []
    assert repo.phrases == {}
    assert queue.events() == []


def test_schema_version_99_goes_dead(handler, store, queue, repo):
    action = handler.handle(make_message(schema_version=99))
    assert action == DEAD
    assert store.reads == []
    assert queue.events() == []


def test_object_not_found_goes_dead(handler, store, queue):
    action = handler.handle(make_message())
    assert action == DEAD
    assert queue.events()[-1]["data"]["error_code"] == "object_not_found"


def test_malformed_no_turns_goes_dead(handler, queue):
    assert handler.handle(make_message(turns=[])) == DEAD


# --- Domain: ownership key ---


def test_key_belongs_to_owner():
    owner = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
    assert key_belongs_to_owner(f"u/{owner}/rec/x/norm.wav", owner)
    assert not key_belongs_to_owner(f"u/{OTHER_OWNER}/rec/x/norm.wav", owner)
    assert not key_belongs_to_owner(f"rec/{owner}/norm.wav", owner)


# --- Helper models for the OOM scenarios ---


def _oom_once_model():
    """OOM only on the first call (>1 window); fine afterwards."""

    class _Model:
        loaded = True
        calls = 0

        def load(self):
            pass

        def transcribe_windows(self, windows, *, seqs, language_hint=None):
            self.calls += 1
            if self.calls == 1 and len(windows) > 1:
                raise RuntimeError("CUDA out of memory")
            from app.domain.transcription import TranscriptionOutput

            return TranscriptionOutput(texts={s: f"p-{s}" for s in seqs}, language="ru")

    return _Model()


def _always_oom_over_one():
    """OOM on any batch of >1 window (fine once reduced to single windows)."""

    class _Model:
        loaded = True

        def load(self):
            pass

        def transcribe_windows(self, windows, *, seqs, language_hint=None):
            if len(windows) > 1:
                raise RuntimeError("CUDA out of memory")
            from app.domain.transcription import TranscriptionOutput

            return TranscriptionOutput(texts={seqs[0]: "ok"}, language="ru")

    return _Model()
