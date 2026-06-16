"""
Backblaze B2 storage backend (S3-compatible via boto3).

B2 exposes a fully S3-compatible API at https://s3.<region>.backblazeb2.com,
so boto3 talks to it unchanged. Presigned URLs work the same way too.

Tip: pair the B2 bucket with a Cloudflare custom hostname — Backblaze and
Cloudflare have a zero-egress agreement, so PDF downloads through CF cost
$0 in B2 egress fees. Presigned URLs that point at the CF hostname work fine
as long as the bucket is configured to allow it.
"""

from __future__ import annotations

from typing import Optional

from ...config import get_settings
from .interface import Storage


class B2Storage(Storage):
    backend = "b2"

    def __init__(self):
        settings = get_settings()
        missing = [
            name for name in (
                "b2_endpoint_url",
                "b2_key_id",
                "b2_application_key",
                "b2_bucket_name",
            )
            if not getattr(settings, name, None)
        ]
        if missing:
            raise RuntimeError(
                f"B2 storage requested but missing env vars: {', '.join(m.upper() for m in missing)}. "
                "Set them in .env (see .env.example) or switch STORAGE_BACKEND back to 'local'."
            )

        # lazy boto3 import so installing without boto3 still works in LocalStorage mode
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = settings.b2_bucket_name
        self.endpoint = settings.b2_endpoint_url
        self.region = settings.b2_region

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=settings.b2_key_id,
            aws_secret_access_key=settings.b2_application_key,
            region_name=self.region,
            # SigV4 is required by B2's S3-compatible endpoint
            config=BotoConfig(signature_version="s3v4"),
        )

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client.exceptions.ClientError:
            return False

    def signed_url(self, key: str, *, expires_seconds: int = 3600) -> Optional[str]:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
