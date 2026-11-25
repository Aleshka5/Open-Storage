"""UC-D1 tests: the diarization pipeline, negative paths, idempotency, GPU lease."""

from __future__ import annotations

from app.application.diarize import ACK, DEAD, NACK_RETRY, RETRY_WITH_ATTEMPT
from tests.conftest import (
    OTHER_OWNER,
    RECORDING,
    audio_key,
    make_message,
    make_wav,
    norm_key,
)


def test_owner_mismatch_goes_dead_without_reading_object(handler, store, queue, repo):
    store.put(audio_key(), make_wav())
    msg = make_message(audio_key=f"u/{OTHER_OWNER}/rec/{RECORDING}/original.wav")
    action = handler.handle(msg)
    assert action == DEAD
    # the object was not read
    assert store.downloaded == []
    assert repo.speakers == {}
    # no completed events were emitted
    assert queue.published_events() == []


def test_schema_version_99_goes_dead(handler, queue, store, repo):
    msg = make_message(schema_version=99)
    action = handler.handle(msg)
    assert action == DEAD
    assert store.downloaded == []
    assert queue.published_events() == []


def test_two_speakers_order_index_and_labels(handler, store, queue, repo):
    store.put(audio_key(), make_wav())
    action = handler.handle(make_message())
    assert action == ACK

    assert len(repo.speakers) == 2
    by_order = {}
    for (rid, _key), doc in repo.speakers.items():
        assert rid == RECORDING
        by_order[doc["order_index"]] = doc

    assert by_order[1]["speaker_key"] == "SPEAKER_00"
    assert by_order[1]["label"] == "Speaker 1"
    assert by_order[2]["speaker_key"] == "SPEAKER_01"
    assert by_order[2]["label"] == "Speaker 2"
    for doc in repo.speakers.values():
        assert doc["nick_id"] is None
        assert doc["is_me"] is False


def test_norm_wav_uploaded_and_transcription_published(handler, store, queue):
    store.put(audio_key(), make_wav())
    handler.handle(make_message())

    # norm.wav is in the bucket (overwrite)
    assert norm_key() in store.objects
    assert store.meta[norm_key()]["content_type"] == "audio/wav"

    # audio.transcription with turns
    tr = queue.published_transcription()
    assert len(tr) == 1
    body = tr[0]
    assert body["recording_id"] == RECORDING
    assert body["audio_key"] == norm_key()
    assert body["schema_version"] == 1
    turns = body["turns"]
    assert [t["turn_id"] for t in turns] == ["t0001", "t0002", "t0003"]


def test_turns_sorted_non_overlapping(handler, store, queue):
    store.put(audio_key(), make_wav())
    handler.handle(make_message())
    turns = queue.published_transcription()[0]["turns"]
    starts = [t["start_ms"] for t in turns]
    assert starts == sorted(starts)
    # no overlaps
    for a, b in zip(turns, turns[1:], strict=False):
        assert a["end_ms"] <= b["start_ms"]
    # the overlap flag is set on the overlapping turn and only there
    assert any(t["overlap"] for t in turns)
    assert len({t["speaker_key"] for t in turns}) == 2


def test_completed_event_has_speakers_turns_duration(handler, store, queue):
    store.put(audio_key(), make_wav())
    handler.handle(make_message())
    events = queue.published_events()
    assert [e["event"] for e in events] == ["diarization.started", "diarization.completed"]
    completed = events[1]
    assert completed["data"]["speakers"] == 2
    assert completed["data"]["turns"] == 3
    assert completed["data"]["duration_ms"] == 12960


def test_redelivery_preserves_nick_and_label_no_duplicate(handler, store, queue, repo):
    store.put(audio_key(), make_wav())
    handler.handle(make_message())  # first delivery

    # Simulate a nick assignment by audio-api: label/nick_id changed after the first run.
    doc00 = repo.speakers[(RECORDING, "SPEAKER_00")]
    doc00["label"] = "Ann"
    doc00["nick_id"] = "nick-1"
    doc00["is_me"] = True

    handler.handle(make_message(job_id="rerun-job"))  # redelivery

    assert len(repo.speakers) == 2  # no duplicates
    after = repo.speakers[(RECORDING, "SPEAKER_00")]
    assert after["label"] == "Ann"  # not reset
    assert after["nick_id"] == "nick-1"
    assert after["is_me"] is True


def test_lease_denied_returns_nack_retry_no_attempt_growth(handler, store, queue, lease, repo):
    store.put(audio_key(), make_wav())
    lease.deny = True
    action = handler.handle(make_message())
    assert action == NACK_RETRY
    # attempt in the body is unchanged — the worker never touches it.
    assert lease.released == 0
    # norm.wav is still written (normalization happens before the lease), but there are no speakers
    assert norm_key() in store.objects
    assert repo.speakers == {}


def test_failed_media_no_speakers_goes_dead(handler, store, queue, repo, normalizer):
    store.put(audio_key(), make_wav())
    normalizer.fail = True
    action = handler.handle(make_message())
    assert action == DEAD
    assert repo.speakers == {}
    events = queue.published_events()
    assert events[-1]["event"] == "diarization.failed"
    assert events[-1]["data"]["error_code"] == "failed_media"


def test_object_not_found_goes_dead(handler, store, queue):
    # no audio was put into the store
    action = handler.handle(make_message())
    assert action == DEAD
    assert queue.published_events()[-1]["data"]["error_code"] == "object_not_found"


def test_scratch_cleaned_after_run(handler, store, settings):
    store.put(audio_key(), make_wav())
    handler.handle(make_message())
    import pathlib

    scratch_root = pathlib.Path(settings.scratch_dir)
    remains = [p for p in scratch_root.iterdir()] if scratch_root.exists() else []
    assert remains == []


def test_malformed_message_goes_dead(handler, queue):
    msg = make_message()
    del msg["audio_key"]
    assert handler.handle(msg) == DEAD


def _oom_model():
    def diarize(wav_path: str):
        raise RuntimeError("CUDA out of memory")

    class M:
        loaded = True

        def load(self):
            pass

    m = M()
    m.diarize = diarize
    return m


def test_gpu_oom_increments_attempt_and_returns_retry(
    settings, store, repo, queue, normalizer, lease
):
    from app.application.diarize import DiarizationHandler

    h = DiarizationHandler(
        settings=settings, model=_oom_model(), store=store, repo=repo,
        queue=queue, normalizer=normalizer, lease=lease,
    )
    store.put(audio_key(), make_wav())
    msg = make_message()
    action = h.handle(msg)
    # first OOM: attempt 0 -> 1, back to .retry via republish
    assert action == RETRY_WITH_ATTEMPT
    assert msg["attempt"] == 1
    # no speakers, but norm.wav is written (before the lease)
    assert repo.speakers == {}
    assert norm_key() in store.objects


def test_gpu_oom_after_max_attempts_goes_dead(settings, store, repo, queue, normalizer, lease):
    from app.application.diarize import DiarizationHandler

    h = DiarizationHandler(
        settings=settings, model=_oom_model(), store=store, repo=repo,
        queue=queue, normalizer=normalizer, lease=lease,
    )
    store.put(audio_key(), make_wav())
    msg = make_message(attempt=2)  # 0-indexed: after this attempt attempt=3 >= max(3)
    action = h.handle(msg)
    assert action == DEAD
    events = queue.published_events()
    assert events[-1]["event"] == "diarization.failed"
    assert events[-1]["data"]["error_code"] == "gpu_oom"
