"""Object storage (MinIO) port for diarizer.

The implementation is synchronous (boto3, called from the worker thread, not the event loop).
download/get/put + existence check. Key contract — minio/bucket-and-keys.md.
"""

from __future__ import annotations

from typing import Protocol


class ObjectStore(Protocol):
    def download(self, key: str, dest_path: str) -> None:
        """Downloads the object to disk. Raises on absence/failure."""

    def upload_file(self, key: str, src_path: str, content_type: str) -> None:
        """Uploads a file to the bucket (overwrite, idempotent)."""

    def exists(self, key: str) -> bool:
        """True if the object exists (for object_not_found diagnostics)."""
