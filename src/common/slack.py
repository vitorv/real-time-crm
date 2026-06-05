"""Slack incoming-webhook notification (FR5).

Posts a "New Lead Alert" carrying the seven required fields. A failed send raises
``SlackError`` so the Enrich Lambda lets SQS retry (target/ writes are idempotent,
so a retry re-sends rather than loses the alert).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

Opener = Callable[..., Any]

# (label, enriched-record key) — order shown in the alert.
_FIELDS: list[tuple[str, str]] = [
    ("Name", "display_name"),
    ("Lead ID", "lead_id"),
    ("Created Date", "date_created"),
    ("Label", "status_label"),
    ("Email", "lead_email"),
    ("Lead Owner", "lead_owner"),
    ("Funnel", "funnel"),
]


class SlackError(Exception):
    """Slack rejected the message or returned an unexpected response."""


def build_message(enriched: dict[str, Any]) -> dict[str, Any]:
    """Build the Slack webhook payload for a New Lead Alert."""
    lines = "\n".join(f"*{label}:* {enriched.get(key)}" for label, key in _FIELDS)
    text = f"*New Lead Alert*\n{lines}"
    return {
        "text": text,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "New Lead Alert"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": lines}},
        ],
    }


def post_new_lead_alert(
    webhook_url: str,
    enriched: dict[str, Any],
    *,
    opener: Opener = urllib.request.urlopen,
    timeout: float = 10.0,
) -> None:
    """POST the New Lead Alert to a Slack incoming webhook."""
    data = json.dumps(build_message(enriched)).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with opener(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8").strip()
    except urllib.error.HTTPError as exc:
        raise SlackError(f"Slack returned HTTP {exc.code}") from exc
    if body and body != "ok":
        raise SlackError(f"unexpected Slack response: {body!r}")
