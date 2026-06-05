"""Lead-owner lookup against the public ``dea-lead-owner`` S3 bucket (FR4).

The file may not exist yet shortly after a lead is created — that's the whole
point of the 10-minute delay. A 404 raises ``LookupNotFound`` so the caller can
let SQS retry (and eventually dead-letter) the message.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

# Injectable for tests; defaults to the real urllib opener.
Opener = Callable[..., Any]


class LookupNotFound(Exception):
    """The owner file for this lead does not exist yet (HTTP 404)."""


def fetch_lead_owner(
    lead_id: str,
    base_url: str,
    *,
    opener: Opener = urllib.request.urlopen,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """GET ``{base_url}/{lead_id}.json`` and return the parsed owner record."""
    url = f"{base_url.rstrip('/')}/{lead_id}.json"
    try:
        with opener(url, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise LookupNotFound(lead_id) from exc
        raise
    if not isinstance(payload, dict):
        raise ValueError(f"lookup for {lead_id} is not a JSON object")
    return payload
