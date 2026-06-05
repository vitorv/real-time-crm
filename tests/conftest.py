"""Shared pytest fixtures.

The autouse ``aws_env`` fixture injects dummy AWS credentials + region so tests
never touch real AWS (the dev machine has live credentials under ~/.aws). Combined
with ``moto``'s ``mock_aws``, all S3 calls stay in-memory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())
