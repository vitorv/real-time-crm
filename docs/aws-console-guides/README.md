# AWS Console Setup Guides

Step-by-step, click-by-click guides for building this project **by hand in the AWS
Management Console** — an alternative to `sam deploy`, written so you can reproduce
(and understand) every resource yourself.

> These mirror what [`template.yaml`](../../template.yaml) provisions automatically.
> In real use you'd run `sam build && sam deploy`; this is the manual, learn-the-pieces path.

## Guides (in order)

| # | Guide | Builds | Project phase |
| --- | --- | --- | --- |
| — | (no guide) | local tooling only — no AWS | Phase 1 (scaffold) |
| 1 | [phase2-ingestion.md](phase2-ingestion.md) | S3 bucket, Ingest Lambda, API Gateway, IAM | Phase 2 (FR1/FR2) |
| 2 | [phase3-delay-enrichment.md](phase3-delay-enrichment.md) | SQS delay queue + DLQ, S3 notification, Enrich Lambda, IAM | Phase 3 (FR3/FR4) |
| 3 | [phase4-slack.md](phase4-slack.md) | Slack incoming webhook + Lambda env var | Phase 4 (FR5) |
| 4 | [phase5-validation.md](phase5-validation.md) | Close subscription + end-to-end test + teardown | Phase 5 |

Follow them in order — Phase 3 depends on the bucket from Phase 2, etc.

---

## Before you start (all guides)

1. An **AWS account** and a sign-in with permissions to create S3, Lambda, API
   Gateway, SQS, and IAM resources (an admin/root-ish user for learning is fine).
2. Sign in at **https://console.aws.amazon.com/**.
3. **Set your Region to `US East (N. Virginia) us-east-1`** using the Region
   selector at the **top-right** of the console. The public lookup bucket
   (`dea-lead-owner`) lives in `us-east-1`, so use it everywhere for consistency.
4. Have your **12-digit AWS Account ID** handy (top-right → your account name →
   the number under "Account ID"). It's used to make the S3 bucket name unique.

> **Note:** The AWS Console UI changes over time. Button/menu labels may differ
> slightly from these steps, but the flow and field names are stable. When in
> doubt, use the search bar at the top of the console to jump to a service.

---

## Naming used throughout

| Resource | Name |
| --- | --- |
| S3 data bucket | `crm-leads-<ACCOUNT_ID>-us-east-1` |
| Ingest Lambda | `crm-ingest-dev` |
| Enrich Lambda | `crm-enrich-dev` |
| Delay queue | `crm-enrich-delay-dev` |
| Dead-letter queue | `crm-enrich-dlq-dev` |
| API | `crm-api` (stage `Prod`, resource `/crm`) |

Replace `<ACCOUNT_ID>` with your real 12-digit account number.

---

## Package the Lambda code (shared by Phase 2 + 3)

Both Lambdas run the same code package (they just use different handlers). Build a
single zip from the `src/` folder once, and upload it to each function.

> ⚠️ **Don't use PowerShell's `Compress-Archive`** for this — on Windows it writes
> zip entries with backslashes, which Linux Lambda can't import (`No module named
> 'common'`). Use the Python command below, which always writes forward slashes.

From the repo root:

```powershell
python -c "import shutil; shutil.make_archive('lambda_package','zip','src')"
```

This produces **`lambda_package.zip`** with `common/`, `ingest/`, and `enrich/` at
the zip root. That layout is what the handlers `ingest.app.lambda_handler` and
`enrich.app.lambda_handler` expect. No third-party dependencies are needed — `boto3`
is already in the Lambda Python runtime, and Slack uses the standard library.

Re-run that command and re-upload whenever you change the code.
