"""Enrich Lambda — lead-owner lookup + merge (FR3 / FR4).

Triggered by the SQS delay queue ~10 minutes after a lead lands in S3 ``source/``.
For each message it:

1. reads the S3 ``ObjectCreated`` notification to find the source object,
2. loads the stored Close event and extracts the ``lead_id``,
3. looks up the lead owner in the public ``dea-lead-owner`` bucket,
4. merges the two by ``lead_id`` and writes the enriched record to ``target/``.

If the owner file is not present yet, ``LookupNotFound`` propagates so SQS retries
the message (and eventually routes it to the dead-letter queue). Phase 4 will add
the Slack notification after the ``target/`` write.
"""

from __future__ import annotations

import json
from typing import Any

from common import s3
from common.config import Config, load_config
from common.logging import configure_logging, get_logger
from common.lookup import fetch_lead_owner
from ingest.app import extract_lead_id

configure_logging()
logger = get_logger("enrich")


def build_enriched(event_payload: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
    """Merge the Close event with the owner lookup into the notification record."""
    event = event_payload.get("event")
    crm = event if isinstance(event, dict) else {}
    data_obj = crm.get("data")
    data: dict[str, Any] = data_obj if isinstance(data_obj, dict) else {}
    return {
        "lead_id": extract_lead_id(event_payload),
        "display_name": data.get("display_name"),
        "date_created": data.get("date_created"),
        "status_label": data.get("status_label"),
        "lead_email": owner.get("lead_email"),
        "lead_owner": owner.get("lead_owner"),
        "funnel": owner.get("funnel"),
    }


def _iter_source_keys(sqs_record: dict[str, Any]) -> list[tuple[str, str]]:
    """Pull (bucket, key) pairs out of an SQS message carrying an S3 event."""
    body = json.loads(sqs_record["body"])
    pairs: list[tuple[str, str]] = []
    for rec in body.get("Records", []):
        s3_info = rec.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = s3_info.get("object", {}).get("key")
        if bucket and key:
            pairs.append((bucket, key))
    return pairs


def _process_source_object(bucket: str, key: str, cfg: Config) -> None:
    event_payload = s3.get_json(bucket, key)
    lead_id = extract_lead_id(event_payload)
    owner = fetch_lead_owner(lead_id, cfg.lookup_base_url)
    enriched = build_enriched(event_payload, owner)
    target_key = f"{cfg.target_prefix}enriched_{lead_id}.json"
    s3.put_json(cfg.data_bucket, target_key, enriched)
    logger.info("enrich.stored", extra={"lead_id": lead_id, "key": target_key})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an SQS batch of delayed S3 notifications."""
    cfg = load_config()
    for record in event.get("Records", []):
        for bucket, key in _iter_source_keys(record):
            _process_source_object(bucket, key, cfg)
    return {"status": "ok"}
