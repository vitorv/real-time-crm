"""Ingest Lambda — Close CRM webhook receiver (FR1 / FR2).

Phase 1: stub that logs the request and returns HTTP 200 so the API Gateway
receiver is deployable end-to-end.

Phase 2 will: (optionally) verify the Close signature, parse the webhook event,
extract the lead fields, and write ``crm_event_{lead_id}.json`` to the S3
``source/`` prefix.
"""

from __future__ import annotations

import json
from typing import Any

from common.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("ingest")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an API Gateway proxy event from the Close webhook."""
    logger.info("ingest.received", extra={"path": event.get("path")})
    # Phase 2: parse event["body"] → write crm_event_{lead_id}.json to S3 source/.
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "ok"}),
    }
