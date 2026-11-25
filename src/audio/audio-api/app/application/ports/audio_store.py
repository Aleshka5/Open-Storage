"""Audio storage port (MinIO)."""
from __future__ import annotations

from typing import Any, Protocol


class AudioStore(Protocol):
    """Writes and reads audio objects in the bucket per the MinIO contract."""

    async def put_object_stream(
        self,
        key: str,
        content_type: str,
        stream,
        *,
        size_hint: int | None = None,
        owner_id: str | None = None,
        recording_id: str | None = None,
    ) -> None:
        """Writes the object as a stream (without buffering all of it in memory)."""
        ...

    async def check(self) -> bool:
        """Whether the bucket is alive (for /health)."""
        ...

    async def stat_object(self, key: str) -> dict | None:
        """Object metadata (size, content-type, etag)."""
        ...

    async def create_multipart(self, key: str, content_type: str) -> str:
        """Opens a multipart upload (CreateMultipartUpload); returns upload_id."""
        ...

    async def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str:
        """Uploads a part (UploadPart); returns the part's ETag."""
        ...

    async def complete_multipart(
        self, key: str, upload_id: str, parts: list[dict[str, Any]]
    ) -> None:
        """Completes the multipart upload (CompleteMultipartUpload)."""
        ...

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        """Aborts the multipart upload (AbortMultipartUpload)."""

    async def get_object_range(
        self, key: str, *, start: int = 0, length: int | None = None
    ) -> tuple[bytes, int]:
        """Reads the object range `[start, start+length)`; returns (data, total_len)."""
        ...
