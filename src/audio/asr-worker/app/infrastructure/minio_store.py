"""Infrastructure: object storage (MinIO) via boto3, synchronous.

asr-worker reads only `norm.wav` (16 kHz mono s16le), windowed via a range request —
the whole file is never downloaded or buffered (ADR-014). Keys are `u/{owner}/rec/{...}`.
The worker runs in its own thread, not in the event loop.
"""

from __future__ import annotations

import logging

import boto3

logger = logging.getLogger(__name__)


class S3ObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        use_path_style: bool,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        if use_path_style:
            self._client.meta.config.s3 = {"addressing_style": "path"}

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("s3_head_miss error=%s", type(exc).__name__)
            return False

    def read_window(self, key: str, *, start_byte: int, num_bytes: int) -> bytes:
        """Reads the object range `[start_byte, start_byte+num_bytes)` (range request).

        `start_byte` is counted from the start of the **data-chunk**, not from the start of
        the file. So we add `data_offset` (the data-chunk offset in the WAV header).
        """
        if num_bytes <= 0:
            return b""
        data_offset = self._data_chunk_offset(key)
        start = data_offset + start_byte
        end = start + num_bytes - 1
        resp = self._client.get_object(
            Bucket=self._bucket,
            Key=key,
            Range=f"bytes={start}-{end}",
        )
        return resp["Body"].read()

    def _data_chunk_offset(self, key: str) -> int:
        """Offset of the `data` chunk in `norm.wav` (RIFF). 44 is not hardcoded: ffmpeg may
        insert LIST/INFO.

        We read the first ~256 bytes and look for the `data` chunk id; if not found — the
        canonical 44.
        """
        try:
            head = self._client.get_object(Bucket=self._bucket, Key=key, Range="bytes=0-256")
            b = head["Body"].read()
        except Exception as exc:  # noqa: BLE001
            logger.debug("s3_header_read_fail error=%s", type(exc).__name__)
            return _CANONICAL_WAV_DATA_OFFSET
        return _find_data_chunk_offset(b)


_CANONICAL_WAV_DATA_OFFSET = 44


def _find_data_chunk_offset(header: bytes) -> int:
    """Finds the `data` chunk offset in the WAV header; canonical 44 on a miss."""
    import struct

    if len(header) < 12 or header[:4] != b"RIFF":
        return _CANONICAL_WAV_DATA_OFFSET
    pos = 12
    while pos + 8 <= len(header):
        chunk_id = header[pos : pos + 4]
        size = struct.unpack("<I", header[pos + 4 : pos + 8])[0]
        if chunk_id == b"data":
            return pos + 8
        # chunks are padded to an even size
        pos += 8 + size + (size & 1)
    return _CANONICAL_WAV_DATA_OFFSET
