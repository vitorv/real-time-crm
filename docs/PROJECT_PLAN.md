# Project Plan — Real-Time CRM Lead Processing and Notification System

> Personal planning + progress notes. Last updated 2026-06-05.
> Companion to the formal requirements ([Real-Time CRM Lead Processing and Notification System.md](Real-Time%20CRM%20Lead%20Processing%20and%20Notification%20System.md))
> and the architecture diagram ([architecture_diagram.png](architecture_diagram.png)).

---

## 1. What this project is

An **event-driven, serverless pipeline on AWS** that captures newly-created leads
from the **Close CRM** via webhook, waits ~10 minutes so the CRM can assign a lead
owner, enriches the lead with owner data from a public lookup, and notifies the
sales team in **Slack** — within seconds of the lead landing.

**Problem it solves:** there's a lag between a lead being created in Close and a
sales rep (owner) being assigned. This pipeline absorbs that lag, then pushes a
complete, enriched "New Lead Alert" to the team so leads get followed up fast.

## 2. Functional requirements

| ID | Requirement | Phase |
| --- | --- | --- |
| FR1 | Capture new leads via a Close webhook subscription | 2 (+ 5 to register) |
| FR2 | Store the raw event as JSON in S3 `source/` (`crm_event_{lead_id}.json`) | 2 |
| FR3 | 10-minute delay before processing (SQS delay queue) | 3 |
| FR4 | Look up the lead owner + merge by `lead_id`, write to S3 `target/` | 3 |
| FR5 | Send a notification (Slack) with the 7 required fields | 4 |

**Notification fields:** Name, Lead ID, Created Date, Label (from the CRM event) +
Email, Lead Owner, Funnel (from the lookup).

## 3. Architecture

![Architecture](architecture_diagram.png)

```
Close CRM ──webhook──▶ API Gateway ─▶ Lambda (Ingest) ─PUT─▶ S3 source/
 (lead.created)         POST /crm       parse event       crm_event_{lead_id}.json
                                                                │ S3 event notification
                                                                ▼
                                                        SQS Delay Queue (600s)
                                                                │ after 10 min
                                                                ▼
   Public S3: dea-lead-owner ◀─GET {lead_id}.json─ Lambda (Enrich) ─PUT─▶ S3 target/
                                                       merge by lead_id   enriched_{lead_id}.json
                                                                │ New Lead Alert
                                                                ▼
                                                             Slack
```

A dead-letter queue backs the delay queue: if the owner file still isn't present
after retries, the message is parked in the DLQ instead of being lost.

## 4. Tech stack & key decisions (ADR-001)

| Concern | Choice |
| --- | --- |
| Cloud / region | AWS, `us-east-1` (matches the public lookup bucket) |
| IaC | **AWS SAM** (`template.yaml`) |
| Compute | AWS Lambda (Ingest + Enrich), runtime **python3.11** |
| Webhook receiver | API Gateway REST, `POST /crm` |
| Storage | S3 — `source/` (raw) + `target/` (enriched) |
| Delay | SQS delay queue, `DelaySeconds=600`, redrive → DLQ (×3) |
| Notification | Slack incoming webhook |
| Language / tooling | Python, ruff + mypy + pytest, GitHub Actions CI |

**Notable decisions:**
- **Signature verification deferred** — the Close `Close-Sig-Hash` check is a no-op
  seam (`verify_signature`) for now; accepted risk, to be added with the signing
  secret later.
- **Idempotency by `lead_id`** — S3 keys are derived from `lead_id`, so re-delivered
  webhooks overwrite rather than duplicate (handles parallel leads, no race).
- **Lookup 404 → retry** — if the owner file isn't ready, the Enrich Lambda raises,
  SQS retries (spaced by the 180s visibility timeout), then dead-letters.
- **Slack failure → retry** — better a rare duplicate alert than a missed one.
- Secrets (Slack URL) stay out of source via a `NoEcho` SAM parameter + env var.

## 5. Phased plan & progress

### Phase 0 — Project setup ✅
Context vault + requirements distilled from the assignment; data dictionary and API
notes captured (Close webhook shape, public `dea-lead-owner` lookup, Slack).

### Phase 1 — Scaffold ✅ (`ddbbc12`)
- SAM `template.yaml` skeleton (S3 data bucket + Ingest function wired to API Gateway).
- `src/common/` — env-driven config + JSON-line logging.
- Tooling: `pyproject.toml` (ruff/mypy/pytest), `requirements-dev.txt`, `.gitignore`.
- CI: `.github/workflows/ci.yml` (lint + type-check + test + `sam validate`).
- **Verified:** ruff + mypy + pytest + sam validate green.

### Phase 2 — Webhook ingestion (FR1/FR2) ✅ (`9c40e63`)
- `src/ingest/app.py`: parse the Close webhook out of the API Gateway envelope
  (handles base64), extract `lead_id` (with `object_id` / `data.id` fallbacks),
  guard for `object_type=lead` + `action=created`, and write the payload to
  `s3://…/source/crm_event_{lead_id}.json`. Returns 400 on a bad body; idempotent.
- `src/common/s3.py` (`put_json`); `verify_signature()` no-op seam.
- Tests built from the two sample payloads via `moto`.

### Phase 3 — Delay + enrichment (FR3/FR4) ✅ (`c7ff89b`)
- `template.yaml`: **DelayQueue** (`DelaySeconds=600`, redrive → **DeadLetterQueue**
  after 3 attempts), S3 `source/` → SQS notification, **EnrichFunction** (SQS trigger).
- `src/enrich/app.py`: read the source event, look up the owner, merge by `lead_id`,
  write `target/enriched_{lead_id}.json`.
- `src/common/lookup.py`: `fetch_lead_owner` against the public bucket; **404 →
  `LookupNotFound`** so SQS retries / dead-letters.

### Phase 4 — Slack notification (FR5) ✅ (`a88f447`)
- `src/common/slack.py`: `build_message` (the 7 fields → text + Slack blocks) and
  `post_new_lead_alert` (`urllib` POST; `SlackError` on failure → SQS retry).
- `src/enrich/app.py`: posts the alert after the `target/` write; **skips when no
  webhook is configured** (`SLACK_WEBHOOK_URL`).
- `SlackWebhookUrl` `NoEcho` SAM parameter → Enrich env.
- **State after Phase 4:** FR1–FR5 all implemented; **27 tests**, ruff + mypy +
  sam validate green.

### Phase 5 — Deploy + end-to-end validation ⬜ (planned)
- `sam build && sam deploy --guided`, passing `SlackWebhookUrl`. Capture the `ApiUrl`.
- Register the **Close webhook subscription** against the `ApiUrl` (coordinate with
  Azmat/Ninad — they hold Close access; our endpoint must exist first).
- End-to-end test: post a sample webhook → confirm `source/` object → wait the
  10-minute delay → confirm `target/` enriched object → confirm Slack alert.
- Optional hardening: enable signature verification once the signing secret is
  available; CloudWatch alarms; push to GitHub remote.

## 6. How to build, test, deploy

```bash
# local dev
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
ruff check . ; mypy src ; pytest

# infra
sam validate --lint
sam build
sam deploy --guided --parameter-overrides SlackWebhookUrl=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

**Prefer the AWS console?** Step-by-step, click-by-click guides for building the same
stack by hand live in [aws-console-guides/](aws-console-guides/) — one per phase
(2 ingestion, 3 delay+enrichment, 4 Slack, 5 validation + teardown).

## 7. Repo map

```
template.yaml          # AWS SAM stack (API GW, Lambdas, S3, SQS + DLQ)
samconfig.toml         # deploy defaults (stack name, region)
src/
  common/              # config, logging, s3, lookup, slack
  ingest/app.py        # Ingest Lambda  (FR1/FR2)
  enrich/app.py        # Enrich Lambda  (FR3/FR4/FR5)
tests/                 # pytest suite (27 tests) + fixtures
docs/                  # requirements, architecture diagram, this plan
.github/workflows/     # CI
```

## 8. Status summary

| Phase | FRs | Status | Commit |
| --- | --- | --- | --- |
| 0 Setup | — | ✅ | — |
| 1 Scaffold | — | ✅ | `ddbbc12` |
| 2 Ingestion | FR1, FR2 | ✅ | `9c40e63` |
| 3 Delay + enrichment | FR3, FR4 | ✅ | `c7ff89b` |
| 4 Slack notification | FR5 | ✅ | `a88f447` |
| 5 Deploy + validation | — | ⬜ planned | — |

**All functional requirements (FR1–FR5) are implemented and tested locally.**
Remaining work is deployment and live end-to-end validation (Phase 5).
