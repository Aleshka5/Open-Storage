"""Infrastructure: object storage (MinIO) via boto3, synchronous.

The worker runs in its own thread, not in the event loop: synchronous boto3 is more appropriate
here than aioboto3. Keys are `u/{owner}/rec/{recording}/...` (minio/bucket-and-keys.md).
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
        self._client.meta.config.s3 = {"addressing_style": "path" if use_path_style else "auto"}

    def download(self, key: str, dest_path: str) -> None:
        self._client.download_file(self._bucket, key, dest_path)

    def upload_file(self, key: str, src_path: str, content_type: str) -> None:
        self._client.upload_file(
            src_path,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("s3_head_miss error=%s", type(exc).__name__)
            return False
