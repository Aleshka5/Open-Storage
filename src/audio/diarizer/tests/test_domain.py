"""Domain tests: key ownership, the norm.wav key, turn sorting, numbering."""

from __future__ import annotations

from app.domain.diarization import (
    Turn,
    build_speakers,
    key_belongs_to_owner,
    norm_key_for,
    sort_turns,
    source_extension,
    validate_no_overlap,
)

OWNER = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
OTHER = "11111111-2222-3333-4444-555555555555"
REC = "3b9c7a54-1e2d-4c88-9f01-77aa0c3e5b21"


def test_key_belongs_to_owner():
    assert key_belongs_to_owner(f"u/{OWNER}/rec/{REC}/original.m4a", OWNER)
    assert not key_belongs_to_owner(f"u/{OTHER}/rec/{REC}/original.m4a", OWNER)
    # a foreign substring does not pass: the prefix must be at the very start
    assert not key_belongs_to_owner(f"x/{OWNER}/rec/{REC}/f", OWNER)
    # no boundary bleed: one owner is a prefix of another owner
    assert not key_belongs_to_owner(f"u/{OWNER}abc/rec/x", OWNER)


def test_norm_key_for():
    assert norm_key_for(OWNER, REC) == f"u/{OWNER}/rec/{REC}/norm.wav"


def test_source_extension():
    assert source_extension(f"u/{OWNER}/rec/{REC}/original.m4a") == "m4a"
    assert source_extension("original") == "bin"
    assert source_extension("noext") == "bin"


def test_sort_turns_by_start():
    turns = [
        Turn("SPEAKER_01", 3520, 8140),
        Turn("SPEAKER_00", 0, 3520),
    ]
    assert [t.start_ms for t in sort_turns(turns)] == [0, 3520]


def test_validate_no_overlap():
    good = [
        Turn("SPEAKER_00", 0, 1000),
        Turn("SPEAKER_01", 1000, 2000),
        Turn("SPEAKER_00", 2000, 3000),
    ]
    assert validate_no_overlap(good)
    bad = [
        Turn("SPEAKER_00", 0, 1500),
        Turn("SPEAKER_01", 1400, 2000),
    ]
    assert not validate_no_overlap(bad)


def test_build_speakers_order_by_first_appearance():
    turns = [
        Turn("SPEAKER_02", 500, 800),
        Turn("SPEAKER_00", 0, 400),
        Turn("SPEAKER_02", 900, 1200),
    ]
    centroids = {
        "SPEAKER_02": [1.0] * 256,
        "SPEAKER_00": [2.0] * 256,
    }
    specs = build_speakers(turns, centroids=centroids)
    keys_in_order = [s.speaker_key for s in specs]
    # SPEAKER_00 appeared first, then SPEAKER_02
    assert keys_in_order == ["SPEAKER_00", "SPEAKER_02"]
    assert specs[0].order_index == 1
    assert specs[1].order_index == 2
    assert specs[0].centroid == [2.0] * 256
