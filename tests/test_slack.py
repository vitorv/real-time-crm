"""Phase 4 — Slack notification tests (FR5)."""

from __future__ import annotations

import json
import urllib.error

import pytest

from common.slack import SlackError, build_message, post_new_lead_alert

ENRICHED = {
    "display_name": "Lowell Bast",
    "lead_id": "lead_niuYPXlw6vnFQIhwZCKDaaKv9XMQs9KA5NgxhNRBgaA",
    "date_created": "2025-05-20T12:14:56.409000+00:00",
    "status_label": "Potential",
    "lead_email": "gatequdit@gmail.com",
    "lead_owner": "Lucija Bitunjac",
    "funnel": "DE ACADEMY Direct VSL",
}


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._data


def test_build_message_includes_all_seven_fields():
    text = build_message(ENRICHED)["text"]
    for value in (
        "Lowell Bast",
        "lead_niuYPXlw6vnFQIhwZCKDaaKv9XMQs9KA5NgxhNRBgaA",
        "Potential",
        "gatequdit@gmail.com",
        "Lucija Bitunjac",
        "DE ACADEMY Direct VSL",
    ):
        assert value in text


def test_post_sends_payload_and_succeeds():
    captured = {}

    def opener(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["method"] = req.get_method()
        return _FakeResp(b"ok")

    assert post_new_lead_alert("https://hooks.slack.test/x", ENRICHED, opener=opener) is None
    assert captured["url"] == "https://hooks.slack.test/x"
    assert captured["method"] == "POST"
    assert "New Lead Alert" in json.loads(captured["body"])["text"]


def test_post_raises_slackerror_on_http_error():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", None, None)

    with pytest.raises(SlackError, match="HTTP 500"):
        post_new_lead_alert("https://x", ENRICHED, opener=opener)


def test_post_raises_slackerror_on_unexpected_body():
    def opener(req, timeout=None):
        return _FakeResp(b"invalid_payload")

    with pytest.raises(SlackError, match="unexpected"):
        post_new_lead_alert("https://x", ENRICHED, opener=opener)
