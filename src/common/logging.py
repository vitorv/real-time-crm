"""Shared structured (JSON-line) logging for all Lambda functions.

One log line per event, JSON-encoded, written to stdout — CloudWatch captures it
as-is. Use the standard ``logging`` API; pass structured fields via ``extra``:

    logger.info("ingest.received", extra={"lead_id": lead_id})
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

# Standard LogRecord attributes — anything outside this set (passed via `extra`)
# is merged into the JSON payload.
_STD_ATTRS = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Format a LogRecord as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
