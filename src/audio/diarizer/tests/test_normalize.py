"""Normalization tests (ffmpeg): 16 kHz mono s16le, length within 1 frame (ADR-014).

These tests depend on ffmpeg being present on the host; they really run the normalization
on synthetic data (no GPU and no Pyannote).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.infrastructure.audio_normalizer import normalize, probe_duration_ms

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg is not installed",
)


def _make_stereo_48k(tmp_path: Path) -> tuple[Path, int]:
    """Stereo 48 kHz 0.25 s via ffmpeg; returns (path, duration in ms)."""
    src = tmp_path / "stereo48k.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.25",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            src,
        ],
        check=True,
        capture_output=True,
    )
    return src, 250


def _ffprobe_fields(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    import json

    return json.loads(out.stdout)["streams"][0]


def test_normalize_produces_16k_mono_s16le(tmp_path):
    src, _ = _make_stereo_48k(tmp_path)
    dst = tmp_path / "norm.wav"
    normalize(str(src), str(dst))
    fields = _ffprobe_fields(dst)
    assert fields["sample_rate"] == "16000"
    assert fields["channels"] == 1
    assert fields["codec_name"] == "pcm_s16le"


def test_normalized_duration_within_one_frame(tmp_path):
    src, duration_ms = _make_stereo_48k(tmp_path)
    dst = tmp_path / "norm.wav"
    normalize(str(src), str(dst))
    normalized_ms = probe_duration_ms(str(dst))
    assert normalized_ms is not None
    # 1 frame @16 kHz = 1/16000 s ≈ 0.0625 ms; tolerance 1 frame.
    assert abs(normalized_ms - duration_ms) <= 1


def test_normalize_missing_audio_raises(tmp_path):
    # A file with no audio track: a silent video -> ffmpeg creates no WAV.
    noaudio = tmp_path / "noaudio.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=black:s=16x16:d=0.1", "-c:v", "libx264", noaudio],
        check=False,
        capture_output=True,
    )
    dst = tmp_path / "norm.wav"
    from app.application.ports.audio_normalizer import NormalizeError

    with pytest.raises(NormalizeError):
        normalize(str(noaudio), str(dst))
