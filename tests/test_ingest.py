"""Phase 2 — Ingest Lambda tests (FR1/FR2)."""

from __future__ import annotations

import base64
import json

import boto3
import pytest
from moto import mock_aws

from ingest.app import (
    WebhookError,
    extract_lead_id,
    lambda_handler,
    parse_webhook,
)

from .conftest import load_fixture

BUCKET = "crm-leads-test"


def api_event(body_obj: dict, *, is_base64: bool = False) -> dict:
    body = json.dumps(body_obj)
    if is_base64:
        body = base64.b64encode(body.encode("utf-8")).decode("utf-8")
    return {"path": "/crm", "httpMethod": "POST", "isBase64Encoded": is_base64, "body": body}


# --- pure parse/extract (no AWS) -------------------------------------------------

def test_parse_webhook_returns_payload_dict():
    payload = load_fixture("close_lead_created_2.json")
    assert parse_webhook(api_event(payload)) == payload


def test_parse_webhook_decodes_base64_body():
    payload = load_fixture("close_lead_created_1.json")
    assert parse_webhook(api_event(payload, is_base64=True)) == payload


def test_parse_webhook_rejects_missing_body():
    with pytest.raises(WebhookError, match="no body"):
        parse_webhook({"path": "/crm"})


def test_parse_webhook_rejects_non_json_body():
    with pytest.raises(WebhookError, match="not valid JSON"):
        parse_webhook({"body": "not-json"})


def test_extract_lead_id_prefers_lead_id():
    payload = load_fixture("close_lead_created_1.json")
    assert extract_lead_id(payload) == "lead_Q6uqUbqVS4NYyHGJnfxpfNKpZ0roxEDCdD9oIAaMJ4z"


def test_extract_lead_id_falls_back_to_object_id():
    payload = {"event": {"object_id": "lead_FROM_OBJECT_ID"}}
    assert extract_lead_id(payload) == "lead_FROM_OBJECT_ID"


def test_extract_lead_id_raises_when_absent():
    with pytest.raises(WebhookError, match="lead_id"):
        extract_lead_id({"event": {"object_type": "lead", "action": "created"}})


# --- handler (S3 via moto) -------------------------------------------------------

@pytest.mark.parametrize(
    "fixture, lead_id",
    [
        ("close_lead_created_1.json", "lead_Q6uqUbqVS4NYyHGJnfxpfNKpZ0roxEDCdD9oIAaMJ4z"),
        ("close_lead_created_2.json", "lead_niuYPXlw6vnFQIhwZCKDaaKv9XMQs9KA5NgxhNRBgaA"),
    ],
)
@mock_aws
def test_handler_stores_event_to_source(monkeypatch, fixture, lead_id):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)

    payload = load_fixture(fixture)
    resp = lambda_handler(api_event(payload), None)

    assert resp["statusCode"] == 200
    key = f"source/crm_event_{lead_id}.json"
    assert json.loads(resp["body"]) == {"status": "ok", "lead_id": lead_id, "key": key}

    stored = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    assert stored == payload


@mock_aws
def test_handler_is_idempotent_per_lead_id(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    payload = load_fixture("close_lead_created_2.json")

    lambda_handler(api_event(payload), None)
    lambda_handler(api_event(payload), None)  # redelivery

    key = "source/crm_event_lead_niuYPXlw6vnFQIhwZCKDaaKv9XMQs9KA5NgxhNRBgaA.json"
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix="source/")
    assert [o["Key"] for o in listing["Contents"]] == [key]


@mock_aws
def test_handler_skips_non_lead_created_event(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", BUCKET)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)

    event = api_event({"event": {"object_type": "lead", "action": "updated", "lead_id": "lead_X"}})
    resp = lambda_handler(event, None)

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"status": "skipped"}
    assert "Contents" not in s3.list_objects_v2(Bucket=BUCKET, Prefix="source/")


def test_handler_returns_400_on_bad_body():
    resp = lambda_handler({"path": "/crm", "body": "not-json"}, None)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["status"] == "error"
