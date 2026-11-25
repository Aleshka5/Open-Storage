"""Audio normalization port (ffmpeg, ADR-014 / D-03).

Flags are fixed by the contract: `ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le`. Decoding
runs on CPU and before the GPU lease. Can be replaced in tests (no ffmpeg spawn).
"""

from __future__ import annotations

from typing import Protocol


class NormalizeError(RuntimeError):
    """ffmpeg failed to decode (no audio, corrupt file) — `.dead (failed_media)`."""


class AudioNormalizer(Protocol):
    def normalize(self, src_path: str, dst_path: str) -> None:
        """Decodes the source into a 16 kHz mono s16le WAV. Raises NormalizeError."""

    def probe_duration_ms(self, path: str) -> int | None:
        """Duration in ms (ffprobe). None if it cannot be read."""
