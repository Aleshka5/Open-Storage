"""MPEG duration / index detection (ADR-010).

An MPEG audio stream without a Xing/VBRI index declares a bitrate estimate as its duration;
the browser then seeks by that wrong length and plays the wrong place. Intake measures the
real length from the frame count and stores a stream that carries an index.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.domain.media import (
    add_stream_index,
    measure_mpeg_duration_ms,
    mpeg_samples_per_frame,
    probe,
)

ffmpeg = shutil.which("ffmpeg") or ""
ffprobe = shutil.which("ffprobe") or ""
needs_ffmpeg = pytest.mark.skipif(not (ffmpeg and ffprobe), reason="ffmpeg is not installed")


def _run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


@pytest.fixture()
def indexless_vbr_mp3(tmp_path: Path) -> Path:
    """A VBR MP3 whose index frame was stripped — the shape the browser mis-times."""
    plain = tmp_path / "plain.mp3"
    _run(
        ffmpeg, "-y", "-v", "error", "-f", "lavfi",
        "-i", "sine=frequency=300:duration=20", "-ac", "1", "-ar", "8000",
        "-c:a", "libmp3lame", "-q:a", "6", str(plain),
    )
    out = tmp_path / "indexless.mp3"
    _run(ffmpeg, "-y", "-v", "error", "-i", str(plain), "-c", "copy", "-write_xing", "0", str(out))
    return out


def test_mpeg_samples_per_frame_follows_the_mpeg_version():
    assert mpeg_samples_per_frame(8000) == 576  # MPEG-2.5
    assert mpeg_samples_per_frame(24000) == 576  # MPEG-2
    assert mpeg_samples_per_frame(44100) == 1152  # MPEG-1
    assert mpeg_samples_per_frame(48000) == 1152


@needs_ffmpeg
def test_measures_the_real_length_of_an_indexless_stream(indexless_vbr_mp3: Path):
    measured = measure_mpeg_duration_ms(indexless_vbr_mp3)
    assert measured is not None
    # 20 s of audio; the encoder padding is under 1%.
    assert 19_000 <= measured <= 20_500


@needs_ffmpeg
def test_probe_flags_an_indexless_stream_and_keeps_the_declared_duration(indexless_vbr_mp3: Path):
    probed = probe(indexless_vbr_mp3)
    assert probed.container == "mp3"
    assert probed.declared_duration_ms is not None
    assert probed.needs_index is True
    # The declared length is the bitrate estimate and disagrees with the frame count.
    assert abs((probed.declared_duration_ms or 0) - (probed.duration_ms or 0)) > 500


@needs_ffmpeg
def test_add_stream_index_writes_a_file_with_a_correct_length(
    indexless_vbr_mp3: Path, tmp_path: Path
):
    dst = tmp_path / "indexed.mp3"
    assert add_stream_index(indexless_vbr_mp3, dst) is True

    probed = probe(dst)
    assert probed.needs_index is False
    assert probed.declared_duration_ms == probed.duration_ms
    # No re-encode: the audio frames survive the remux.
    frames_before = _frame_count(indexless_vbr_mp3)
    assert _frame_count(dst) == frames_before


@needs_ffmpeg
def test_a_stream_that_already_has_an_index_is_left_alone(tmp_path: Path):
    plain = tmp_path / "plain.mp3"
    _run(
        ffmpeg, "-y", "-v", "error", "-f", "lavfi",
        "-i", "sine=frequency=300:duration=20", "-ac", "1", "-ar", "8000",
        "-c:a", "libmp3lame", "-q:a", "6", str(plain),
    )
    probed = probe(plain)
    assert probed.needs_index is False


def _frame_count(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0", "-count_frames",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return int(out.stdout.decode().strip().strip(","))
