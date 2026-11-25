"""asr-worker domain tests: batches, ownership key, windows."""

from __future__ import annotations

from app.domain.transcription import Turn, build_batches, key_belongs_to_owner, owner_prefix
from app.infrastructure.minio_store import _find_data_chunk_offset
from app.infrastructure.parakeet_model import window_byte_range


def test_owner_prefix_and_key_check():
    owner = "9f1d2c33-8a44-4b0e-8f5e-1c2d3e4f5a60"
    assert owner_prefix(owner) == f"u/{owner}/"
    assert key_belongs_to_owner(f"u/{owner}/rec/abc/norm.wav", owner)
    assert not key_belongs_to_owner("rec/abc/norm.wav", owner)
    assert not key_belongs_to_owner("u/other/rec/abc/norm.wav", owner)


def test_build_batches_by_turns_limit():
    turns = [
        Turn(turn_id=f"t{i}", speaker_key="S", start_ms=i * 1000, end_ms=i * 1000 + 800, seq=i)
        for i in range(1, 16)
    ]
    batches = build_batches(turns, max_turns=8, max_seconds=60)
    assert [len(b) for b in batches] == [8, 7]


def test_build_batches_by_seconds_limit():
    turns = [
        Turn(turn_id="t1", speaker_key="S", start_ms=0, end_ms=30_000, seq=1),
        Turn(turn_id="t2", speaker_key="S", start_ms=30_000, end_ms=60_000, seq=2),
        Turn(turn_id="t3", speaker_key="S", start_ms=60_000, end_ms=90_000, seq=3),
    ]
    # 60 s per batch: t1+t2 = 60 s (exactly), t3 separately.
    batches = build_batches(turns, max_turns=8, max_seconds=60)
    assert [len(b) for b in batches] == [2, 1]


def test_window_byte_range():
    # s16le 16 kHz mono = 32000 bytes/s → 32 bytes/ms.
    start_byte, num_bytes = window_byte_range(0, 3520)
    assert start_byte == 0
    assert num_bytes == 3520 * 32
    start_byte, num_bytes = window_byte_range(1000, 2000)
    assert start_byte == 32_000
    assert num_bytes == 32_000


def test_order_preserved_in_batches():
    # the turn order is preserved: seq grows, batches do not reorder.
    turns = [
        Turn(turn_id=f"t{i}", speaker_key="S", start_ms=i * 10, end_ms=i * 10 + 5, seq=i)
        for i in range(1, 10)
    ]
    batches = build_batches(turns, max_turns=4, max_seconds=60)
    flat = [t.seq for b in batches for t in b]
    assert flat == list(range(1, 10))


def test_data_chunk_offset_canonical_wav():
    # Canonical WAV: RIFF + fmt (16) + data → the data chunk at 44 bytes.
    header = (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + b"\x00" * 16
        + b"data"
        + b"\x00\x00\x00\x00"
    )
    assert _find_data_chunk_offset(header) == 44


def test_data_chunk_offset_with_extra_chunk():
    # ffmpeg may insert LIST/INFO before data — the offset is not 44.
    header = (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WAVE"
        + b"LIST"
        + (10).to_bytes(4, "little")
        + b"\x00" * 10
        + b"data"
        + b"\x00\x00\x00\x00"
    )
    offset = _find_data_chunk_offset(header)
    # 12 (RIFF+hdr) + 8 (LIST id+size) + 10 (data) = 30; data chunk payload +8 = 38
    assert offset == 38


def test_data_chunk_offset_non_riff_falls_back():
    assert _find_data_chunk_offset(b"not a wav") == 44
