"""MinIO: writes audio objects to the bucket asynchronously (aioboto3).

The `original.*` object is written as a stream; the `x-amz-meta-owner` /
`x-amz-meta-recording` metadata come from the bucket-and-keys.md contract.
"""

from __future__ import annotations

import logging
from typing import Any

from aioboto3 import Session
from botocore.config import Config

logger = logging.getLogger(__name__)


class MinioAudioStore:
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
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._region = region
        self._use_path_style = use_path_style
        self._session = Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def _client(self):
        # aioboto3 15.x rejects `use_path_style` as a client kwarg — it raises
        # `TypeError: Session.client() got an unexpected keyword argument` at call time,
        # which surfaces as `minio: down` on /health and every upload failing.
        # The addressing style belongs in `Config`.
        config = Config(
            s3={"addressing_style": "path" if self._use_path_style else "auto"},
        )
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            config=config,
        )

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
        metadata: dict[str, str] = {"owner": owner_id or "", "recording": recording_id or ""}
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=stream,
                ContentType=content_type,
                Metadata=metadata,
            )

    async def check(self) -> bool:
        try:
            async with self._client() as s3:
                # head_bucket is not available on every MinIO; we use list_objects_v2 with a limit.
                await s3.list_objects_v2(Bucket=self._bucket, MaxKeys=1)
            return True
        except Exception as exc:  # noqa: BLE001 — status on any failure
            logger.warning("minio_check_failed error=%s", type(exc).__name__)
            return False

    async def stat_object(self, key: str) -> dict | None:
        try:
            async with self._client() as s3:
                head = await s3.head_object(Bucket=self._bucket, Key=key)
                return {
                    "size": head.get("ContentLength"),
                    "content_type": head.get("ContentType"),
                    "etag": head.get("ETag"),
                }
        except Exception:  # noqa: BLE001
            return None

    async def create_multipart(self, key: str, content_type: str) -> str:
        async with self._client() as s3:
            res = await s3.create_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                ContentType=content_type,
            )
            return res["UploadId"]

    async def upload_part(
        self, key: str, upload_id: str, part_number: int, data: bytes
    ) -> str:
        async with self._client() as s3:
            res = await s3.upload_part(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=data,
            )
            return res["ETag"]

    async def complete_multipart(
        self, key: str, upload_id: str, parts: list[dict[str, Any]]
    ) -> None:
        async with self._client() as s3:
            await s3.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            async with self._client() as s3:
                await s3.abort_multipart_upload(
                    Bucket=self._bucket, Key=key, UploadId=upload_id
                )
        except Exception as exc:  # noqa: BLE001 — the abort is unconditional
            logger.warning(
                "minio_abort_multipart_error error=%s", type(exc).__name__
            )

    async def get_object_range(
        self, key: str, *, start: int = 0, length: int | None = None
    ) -> tuple[bytes, int]:
        rng = f"bytes={start}-" if length is None else f"bytes={start}-{start + length - 1}"
        async with self._client() as s3:
            head = await s3.head_object(Bucket=self._bucket, Key=key)
            total = int(head.get("ContentLength") or 0)
            resp = await s3.get_object(Bucket=self._bucket, Key=key, Range=rng)
            body = await resp["Body"].read()
        return body, total
