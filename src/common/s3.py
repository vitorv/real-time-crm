"""Thin S3 helpers shared by the Lambda functions.

A new boto3 client is created per call — cheap, and keeps the functions trivially
testable under ``moto`` (no module-level client captured before the mock starts).
"""

from __future__ import annotations

import json
from typing import Any

import boto3


def put_json(bucket: str, key: str, obj: Any) -> None:
    """Write ``obj`` as pretty JSON to ``s3://bucket/key``."""
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(obj, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(bucket: str, key: str) -> Any:
    """Read and parse JSON from ``s3://bucket/key``."""
    resp = boto3.client("s3").get_object(Bucket=bucket, Key=key)
    return json.loads(resp["Body"].read())
