"""Ingest Lambda — Close CRM webhook receiver (FR1 / FR2).

Receives the Close ``lead.created`` webhook through API Gateway (`POST /crm`),
extracts the Close payload from the API Gateway envelope, and writes it to the
S3 ``source/`` prefix as ``crm_event_{lead_id}.json``.

Signature verification (``Close-Sig-Hash``) is intentionally deferred — see
ADR-001. ``verify_signature`` is a no-op seam so it can be added without
reshaping the handler.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from common import s3
from common.config import load_config
from common.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("ingest")


class WebhookError(Exception):
    """Raised when an incoming request is not a usable Close webhook."""


def verify_signature(event: dict[str, Any]) -> None:
    """Deferred (ADR-001): seam for Close-Sig-Hash verification. Currently a no-op."""
    return None


def _decode_body(event: dict[str, Any]) -> str:
    body = event.get("body")
    if body is None:
        raise WebhookError("request has no body")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise WebhookError(f"body is not valid base64: {exc}") from exc
    return body


def parse_webhook(event: dict[str, Any]) -> dict[str, Any]:
    """Decode the API Gateway envelope into the Close webhook payload (a dict)."""
    raw = _decode_body(event)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise WebhookError(f"body is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WebhookError("webhook payload is not a JSON object")
    return payload


def _event_obj(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event")
    return event if isinstance(event, dict) else {}


def extract_lead_id(payload: dict[str, Any]) -> str:
    """Find the lead id in a Close event payload, with sensible fallbacks."""
    crm = _event_obj(payload)
    data_obj = crm.get("data")
    data: dict[str, Any] = data_obj if isinstance(data_obj, dict) else {}
    lead_id = crm.get("lead_id") or crm.get("object_id") or data.get("id")
    if not lead_id:
        raise WebhookError("could not determine lead_id from payload")
    return str(lead_id)


def _is_lead_created(payload: dict[str, Any]) -> bool:
    crm = _event_obj(payload)
    return crm.get("object_type") == "lead" and crm.get("action") == "created"


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an API Gateway proxy event from the Close webhook."""
    cfg = load_config()
    verify_signature(event)

    try:
        payload = parse_webhook(event)
    except WebhookError as exc:
        logger.error("ingest.bad_request", extra={"error": str(exc)})
        return _response(400, {"status": "error", "message": str(exc)})

    if not _is_lead_created(payload):
        crm = _event_obj(payload)
        logger.info(
            "ingest.skipped",
            extra={"object_type": crm.get("object_type"), "action": crm.get("action")},
        )
        return _response(200, {"status": "skipped"})

    try:
        lead_id = extract_lead_id(payload)
    except WebhookError as exc:
        logger.error("ingest.bad_request", extra={"error": str(exc)})
        return _response(400, {"status": "error", "message": str(exc)})

    key = f"{cfg.source_prefix}crm_event_{lead_id}.json"
    s3.put_json(cfg.data_bucket, key, payload)
    logger.info("ingest.stored", extra={"lead_id": lead_id, "bucket": cfg.data_bucket, "key": key})
    return _response(200, {"status": "ok", "lead_id": lead_id, "key": key})
