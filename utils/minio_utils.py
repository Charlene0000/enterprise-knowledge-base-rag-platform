"""Lazy MinIO client construction with private buckets by default."""

from __future__ import annotations

import json
from threading import Lock

from minio import Minio

from config.minio_config import minio_config


_minio_client: Minio | None = None
_minio_lock = Lock()


def _validate_config() -> None:
    missing = [
        name
        for name, value in {
            "MINIO_ENDPOINT": minio_config.endpoint,
            "MINIO_ACCESS_KEY": minio_config.access_key,
            "MINIO_SECRET_KEY": minio_config.secret_key,
            "MINIO_BUCKET_NAME": minio_config.bucket_name,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"MinIO configuration is incomplete: {', '.join(missing)}")


def _allow_public_reads(client: Minio) -> None:
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{minio_config.bucket_name}/*",
            }
        ],
    }
    client.set_bucket_policy(minio_config.bucket_name, json.dumps(policy))


def get_minio_client() -> Minio:
    global _minio_client
    if _minio_client is None:
        with _minio_lock:
            if _minio_client is None:
                _validate_config()
                client = Minio(
                    endpoint=minio_config.endpoint,
                    access_key=minio_config.access_key,
                    secret_key=minio_config.secret_key,
                    secure=minio_config.secure,
                )
                if not client.bucket_exists(minio_config.bucket_name):
                    client.make_bucket(minio_config.bucket_name)
                if minio_config.public_read:
                    _allow_public_reads(client)
                _minio_client = client
    return _minio_client
