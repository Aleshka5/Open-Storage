"""Domain tests: indexes match data-model.md, ownership map, status ranks."""
from __future__ import annotations

from app.domain.recording import COLLECTIONS, UNIQUE_INDEX_KEYS, audio_key_for
from app.domain.status import RecordingStatus, can_advance, status_rank


def test_five_collections_have_indexes():
    assert set(COLLECTIONS.keys()) == {
        "recordings",
        "speakers",
        "phrases",
        "nicks",
        "owner_voices",
    }


def test_recordings_indexes_match_data_model():
    idx = COLLECTIONS["recordings"]
    assert [("owner_user_id", 1), ("created_at", -1)] in idx
    assert [("owner_user_id", 1), ("kind", 1), ("is_default_voice", 1)] in idx
    assert [("status", 1), ("processing.updated_at", 1)] in idx


def test_speakers_unique_index_keys():
    assert UNIQUE_INDEX_KEYS["speakers"] == ["recording_id", "order_index"]
    assert UNIQUE_INDEX_KEYS["phrases"] == ["recording_id", "seq"]
    assert UNIQUE_INDEX_KEYS["nicks"] == ["owner_user_id", "name_key"]


def test_audio_key_prefix():
    key = audio_key_for("9f1d2c33", "3b9c7a54", "m4a")
    assert key == "u/9f1d2c33/rec/3b9c7a54/original.m4a"


def test_status_rank_monotonic():
    assert status_rank(RecordingStatus.UPLOADED) == 0
    assert status_rank(RecordingStatus.DIARIZING) == 1
    assert status_rank(RecordingStatus.TRANSCRIBING) == 2
    assert status_rank(RecordingStatus.READY) == 3
    assert status_rank(RecordingStatus.FAILED) == -1


def test_can_advance_rules():
    assert can_advance(RecordingStatus.UPLOADED, RecordingStatus.DIARIZING)
    assert can_advance(RecordingStatus.DIARIZING, RecordingStatus.TRANSCRIBING)
    assert can_advance(RecordingStatus.TRANSCRIBING, RecordingStatus.READY)
    # a late duplicate does not roll back
    assert not can_advance(RecordingStatus.TRANSCRIBING, RecordingStatus.DIARIZING)
    # a ready status is not rolled back to failed
    assert not can_advance(RecordingStatus.READY, RecordingStatus.FAILED)
    # failed applies from diarizing/transcribing
    assert can_advance(RecordingStatus.DIARIZING, RecordingStatus.FAILED)
