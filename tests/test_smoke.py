"""Phase 1 smoke tests — the scaffold imports and the stub handler responds."""

from __future__ import annotations

import json

from common.config import load_config
from common.logging import JsonFormatter, configure_logging, get_logger


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    cfg = load_config()
    assert cfg.region == "us-east-1"
    assert cfg.source_prefix == "source/"
    assert cfg.target_prefix == "target/"


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "my-bucket")
    cfg = load_config()
    assert cfg.data_bucket == "my-bucket"


def test_json_formatter_emits_extra_fields():
    configure_logging("INFO")
    logger = get_logger("test")
    record = logger.makeRecord(
        "test", 20, __file__, 1, "hello", None, None, extra={"lead_id": "lead_1"}
    )
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["lead_id"] == "lead_1"
