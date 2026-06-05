"""Phase 3 — Enrich Lambda + lookup tests (FR3/FR4)."""

from __future__ import annotations

import json
import urllib.error

import boto3
import pytest
from moto import mock_aws

from common.lookup import LookupNotFound, fetch_lead_owner
from enrich.app import build_enriched, lambda_handler

from .conftest import load_fixture

BUCKET = "crm-leads-test"


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._data


def sqs_event(bucket: str, key: str) -> dict:
    s3_event = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
    return {"Records": [{"body": json.dumps(s3_event)}]}


# --- lookup (no network) ---------------------------------------------------------

def test_fetch_lead_owner_parses_response():
    owner = {"lead_owner": "Lucija Bitunjac"}

    def opener(url, timeout=None):
        return _FakeResp(json.dumps(owner).encode("utf-8"))

    assert fetch_lead_owner("lead_1", "https://base", opener=opener) == owner


def test_fetch_lead_owner_404_raises_lookup_not_found():
    def opener(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    with pytest.raises(LookupNotFound):
        fetch_lead_owner("lead_1", "https://base", opener=opener)


def test_fetch_lead_owner_other_http_error_propagates():
    def opener(url, timeout=None):
        raise urllib.error.HTTPError(url, 500, "Server Error", None, None)

    with pytest.raises(urllib.error.HTTPError):
        fetch_lead_owner("lead_1", "https://base", opener=opener)


# --- merge (pure) ----------------------------------------------------------------

def test_build_enriched_merges_event_and_owner():
    payload = load_fixture("close_lead_created_2.json")
    owner = load_fixture("lead_owner_2.json")
    assert build_enriched(payload, owner) == {
        "lead_id": "lead_niuYPXlw6vnFQIhwZCKDaaKv9XMQs9KA5NgxhNRBgaA",
        "display_name": "Lowell Bast",
        "date_created": "2025-05-20T12:14:56.409000+00:00",
        "status_label": "Potential",
        "lead_email": "gatequdit@gmail.com",
        "lead_owner": "Lucija Bitunjac",
        "funnel": "DE ACADEMY Direct VSL",
    }


# --- handler (S3 via moto, lookup mocked) ----------------------------------------

@mock_aws
def test_handler_enriches_and_writes_target(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3c = boto3.client("s3", region_name="us-east-1")
    s3c.create_bucket(Bucket=BUCKET)

    payload = load_fixture("close_lead_created_2.json")
    owner = load_fixture("lead_owner_2.json")
    lead_id = payload["event"]["lead_id"]
    src_key = f"source/crm_event_{lead_id}.json"
    s3c.put_object(Bucket=BUCKET, Key=src_key, Body=json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr("enrich.app.fetch_lead_owner", lambda lid, url: owner)

    resp = lambda_handler(sqs_event(BUCKET, src_key), None)

    assert resp == {"status": "ok"}
    target_key = f"target/enriched_{lead_id}.json"
    enriched = json.loads(s3c.get_object(Bucket=BUCKET, Key=target_key)["Body"].read())
    assert enriched["lead_id"] == lead_id
    assert enriched["display_name"] == "Lowell Bast"
    assert enriched["lead_email"] == "gatequdit@gmail.com"
    assert enriched["lead_owner"] == "Lucija Bitunjac"
    assert enriched["funnel"] == "DE ACADEMY Direct VSL"


@mock_aws
def test_handler_propagates_lookup_not_found_for_retry(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3c = boto3.client("s3", region_name="us-east-1")
    s3c.create_bucket(Bucket=BUCKET)

    payload = load_fixture("close_lead_created_2.json")
    lead_id = payload["event"]["lead_id"]
    src_key = f"source/crm_event_{lead_id}.json"
    s3c.put_object(Bucket=BUCKET, Key=src_key, Body=json.dumps(payload).encode("utf-8"))

    def _raise(lid, url):
        raise LookupNotFound(lid)

    monkeypatch.setattr("enrich.app.fetch_lead_owner", _raise)

    with pytest.raises(LookupNotFound):
        lambda_handler(sqs_event(BUCKET, src_key), None)


def _seed_source(monkeypatch):
    """Create the bucket + a source object; mock the owner lookup. Returns (s3, lead_id, key)."""
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3c = boto3.client("s3", region_name="us-east-1")
    s3c.create_bucket(Bucket=BUCKET)
    payload = load_fixture("close_lead_created_2.json")
    owner = load_fixture("lead_owner_2.json")
    lead_id = payload["event"]["lead_id"]
    src_key = f"source/crm_event_{lead_id}.json"
    s3c.put_object(Bucket=BUCKET, Key=src_key, Body=json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr("enrich.app.fetch_lead_owner", lambda lid, url: owner)
    return s3c, lead_id, src_key


@mock_aws
def test_handler_sends_slack_alert_when_configured(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    _, lead_id, src_key = _seed_source(monkeypatch)
    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "enrich.app.post_new_lead_alert", lambda url, enriched: sent.append((url, enriched))
    )

    lambda_handler(sqs_event(BUCKET, src_key), None)

    assert len(sent) == 1
    url, enriched = sent[0]
    assert url == "https://hooks.slack.test/x"
    assert enriched["lead_id"] == lead_id
    assert enriched["lead_owner"] == "Lucija Bitunjac"


@mock_aws
def test_handler_skips_slack_when_no_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    _, _, src_key = _seed_source(monkeypatch)
    calls: list[int] = []
    monkeypatch.setattr("enrich.app.post_new_lead_alert", lambda url, enriched: calls.append(1))

    lambda_handler(sqs_event(BUCKET, src_key), None)

    assert calls == []
