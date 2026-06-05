"""Environment-driven configuration shared by the Lambda functions.

All values come from environment variables set in the SAM template (`template.yaml`),
so the same code runs locally (tests / `sam local`) and in deployed Lambdas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    data_bucket: str
    region: str
    source_prefix: str
    target_prefix: str


def load_config() -> Config:
    """Build a Config from the current environment, with sensible defaults."""
    return Config(
        data_bucket=os.environ.get("DATA_BUCKET", ""),
        region=os.environ.get("AWS_REGION", "us-east-1"),
        source_prefix=os.environ.get("SOURCE_PREFIX", "source/"),
        target_prefix=os.environ.get("TARGET_PREFIX", "target/"),
    )
