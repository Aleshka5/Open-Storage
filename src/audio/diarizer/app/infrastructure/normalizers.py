"""Adapter of the `AudioNormalizer` port to the ffmpeg/ffprobe functions.

Separates the pure functions (audio_normalizer.py) from the port object so subprocess details
do not leak into the application layer.
"""

from __future__ import annotations

from app.infrastructure.audio_normalizer import normalize, probe_duration_ms


class NormalizerAdapter:
    """FFmpeg implementation of 16 kHz mono s16le normalization."""

    @staticmethod
    def normalize(src_path: str, dst_path: str) -> None:
        normalize(src_path, dst_path)

    @staticmethod
    def probe_duration_ms(path: str) -> int | None:
        return probe_duration_ms(path)
