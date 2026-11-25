"""Turn merging before transcription.

Parakeet detects the language per window: a 20–400 ms turn of a Russian conversation comes
back as English or Polish junk ("Oh.", "A jednak.") because there is not enough audio to
decide. Such turns are merged into their neighbours first, so each window carries speech.
"""

from __future__ import annotations

from app.domain.transcription import Turn, merge_short_turns


def turn(turn_id: str, speaker: str, start: int, end: int, overlap: bool = False) -> Turn:
    return Turn(turn_id=turn_id, speaker_key=speaker, start_ms=start, end_ms=end, overlap=overlap)


def spans(turns: list[Turn]) -> list[tuple[str, int, int]]:
    return [(t.speaker_key, t.start_ms, t.end_ms) for t in turns]


def test_a_short_turn_joins_the_same_speaker_neighbour():
    turns = [
        turn("t1", "juri", 5752, 8063),
        turn("t2", "juri", 8110, 8590),  # 47 ms pause → one utterance
    ]
    merged = merge_short_turns(turns)
    assert spans(merged) == [("juri", 5752, 8590)]


def test_a_short_slice_of_another_speaker_is_absorbed_by_the_neighbour():
    # The diarizer's 152 ms bleed-over: "What?" in the real recording.
    turns = [
        turn("t1", "juri", 5752, 8063),
        turn("t2", "olga", 8063, 8215),
        turn("t3", "juri", 8215, 11523),
    ]
    merged = merge_short_turns(turns)
    assert len(merged) == 1
    assert merged[0].start_ms == 5752
    assert merged[0].end_ms == 11523
    # Attributed to the widest participant, not to the sliver.
    assert merged[0].speaker_key == "juri"


def test_normal_turns_are_left_alone():
    turns = [
        turn("t1", "juri", 0, 2300),
        turn("t2", "olga", 2500, 5200),
        turn("t3", "juri", 5400, 8100),
    ]
    assert spans(merge_short_turns(turns)) == spans(turns)


def test_a_long_pause_keeps_two_turns_of_the_same_speaker_apart():
    turns = [
        turn("t1", "juri", 0, 2000),
        turn("t2", "juri", 2400, 4000),  # 400 ms pause > MERGE_GAP_MS
    ]
    assert spans(merge_short_turns(turns)) == spans(turns)


def test_overlapping_turns_are_not_cross_merged():
    turns = [
        turn("t1", "juri", 0, 2000),
        turn("t2", "olga", 1900, 2050, overlap=True),
    ]
    merged = merge_short_turns(turns)
    assert spans(merged) == spans(turns)


def test_merging_can_cascade_but_is_bounded_by_the_window():
    # 12 identical 100 ms slices in a row, 50 ms apart — none is recognisable on its own.
    turns = [turn(f"t{i}", "juri", i * 150, i * 150 + 100) for i in range(12)]
    merged = merge_short_turns(turns)
    assert len(merged) < len(turns)
    assert all(t.end_ms - t.start_ms <= 12_000 for t in merged)
    # Nothing is lost: the union still covers the whole stretch.
    assert merged[0].start_ms == 0
    assert merged[-1].end_ms == turns[-1].end_ms


def test_seq_is_left_for_the_caller():
    merged = merge_short_turns([turn("t1", "juri", 0, 100)])
    assert merged[0].seq == 0
