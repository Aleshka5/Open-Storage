"""Object storage (MinIO) port for asr-worker.

asr-worker reads only `norm.wav` (16 kHz mono s16le) from an `audio.transcription` job,
windowed via seek — the whole file is never downloaded or buffered. The key contract is
minio/bucket-and-keys.md. The implementation is synchronous (boto3, worker thread).
"""

from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def exists(self, key: str) -> bool:
        """True if the object exists (for object_not_found diagnostics)."""

    def read_window(self, key: str, *, start_byte: int, num_bytes: int) -> bytes:
        """Reads the object range `[start_byte, start_byte+num_bytes)`.

        For s16le 16 kHz mono WAV: 32 bytes per ms. The implementation issues a range
        request instead of pulling the whole object.
        """
