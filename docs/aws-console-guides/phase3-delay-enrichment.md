# Phase 3 — Delay + Enrichment (Console Guide)

**Builds:** a **dead-letter queue**, a **10-minute SQS delay queue**, an **S3 event
notification** that feeds the queue, and the **Enrich** Lambda that reads the source
event, looks up the lead owner, merges, and writes `s3://…/target/`.

**Covers:** FR3 (10-min delay) + FR4 (lookup + merge → target).

**Prerequisites:** finish [phase2-ingestion.md](phase2-ingestion.md) (bucket +
Ingest exist). Be in **us-east-1**. Have `lambda_package.zip` ready.

```
S3 source/ ─(ObjectCreated)▶ SQS delay queue (10 min) ─▶ Enrich Lambda ─▶ S3 target/
                                     │ (failures ×3)              │ GET
                                     ▼                            ▼
                              Dead-letter queue        public dea-lead-owner bucket
```

> **Order matters:** create the DLQ first, then the delay queue (it references the
> DLQ), then the queue policy, then the S3 notification (S3 validates it can send to
> the queue), then the Enrich Lambda.

---

## Step 1 — Create the dead-letter queue (DLQ)

1. In the console search bar, type **SQS** and open **Simple Queue Service**.
2. Click **Create queue**.
3. **Type:** **Standard**.
4. **Name:** `crm-enrich-dlq-dev`.
5. Under **Configuration**, set **Message retention period** to **14 Days**.
6. Leave everything else default. Click **Create queue**.

---

## Step 2 — Create the delay queue

1. SQS → **Create queue**.
2. **Type:** **Standard**.
3. **Name:** `crm-enrich-delay-dev`.
4. Under **Configuration**:
   - **Visibility timeout:** **3 Minutes** (180s — must be ≥ the Lambda timeout; it
     also spaces out retries).
   - **Delivery delay:** **10 Minutes** (600s — this is the FR3 buffer; every message
     entering the queue waits 10 minutes before it can be received).
   - **Message retention period:** leave 4 days (default).
5. Scroll to **Dead-letter queue** → toggle **Enabled**.
   - **Choose queue:** select the ARN of `crm-enrich-dlq-dev`.
   - **Maximum receives:** **3**.
6. Click **Create queue**.
7. On the queue's detail page, copy its **ARN** and **URL** (under Details) — you'll
   need the ARN for the policy and the S3 notification.

---

## Step 3 — Let S3 send messages to the delay queue

S3 can only deliver event notifications to a queue whose policy allows it.

1. Open **SQS** → `crm-enrich-delay-dev` → **Access policy** tab → **Edit**.
2. Replace the policy with the following (substitute `<ACCOUNT_ID>` **and** confirm
   the queue ARN matches yours):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3SendMessage",
      "Effect": "Allow",
      "Principal": { "Service": "s3.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:us-east-1:<ACCOUNT_ID>:crm-enrich-delay-dev",
      "Condition": {
        "ArnLike": { "aws:SourceArn": "arn:aws:s3:::crm-leads-<ACCOUNT_ID>-us-east-1" },
        "StringEquals": { "aws:SourceAccount": "<ACCOUNT_ID>" }
      }
    }
  ]
}
```

3. Click **Save**.

> The `Condition` block restricts sends to *your* bucket only — without it any S3
> bucket in AWS could push to your queue.

---

## Step 4 — Wire the S3 → SQS event notification

1. Open **S3** → your bucket `crm-leads-<ACCOUNT_ID>-us-east-1` → **Properties** tab.
2. Scroll to **Event notifications** → **Create event notification**.
3. **Event name:** `source-object-created`.
4. **Prefix:** `source/` (so only new leads, not enriched output, trigger it).
5. **Event types:** check **All object create events** (`s3:ObjectCreated:*`).
6. Scroll to **Destination** → choose **SQS queue** → **Choose from your SQS queues**
   → select `crm-enrich-delay-dev`.
7. Click **Save changes**. If you get *"Unable to validate the following destination
   configurations"*, the queue policy (Step 3) isn't right — re-check the ARNs.

---

## Step 5 — Create the Enrich Lambda

1. **Lambda** → **Create function** → **Author from scratch**.
2. **Function name:** `crm-enrich-dev`.
3. **Runtime:** **Python 3.11**. **Architecture:** **x86_64**.
4. Leave **Create a new role with basic Lambda permissions**. Click **Create
   function**.

### Upload the code + handler
5. **Code** tab → **Upload from** → **.zip file** → upload **`lambda_package.zip`** →
   **Save**.
6. **Runtime settings** → **Edit** → **Handler:** `enrich.app.lambda_handler` → **Save**.

### Environment variables
7. **Configuration** → **Environment variables** → **Edit** → add:

| Key | Value |
| --- | --- |
| `DATA_BUCKET` | `crm-leads-<ACCOUNT_ID>-us-east-1` |
| `SOURCE_PREFIX` | `source/` |
| `TARGET_PREFIX` | `target/` |
| `LOOKUP_BASE_URL` | `https://dea-lead-owner.s3.us-east-1.amazonaws.com` |
| `LOG_LEVEL` | `INFO` |

(We'll add `SLACK_WEBHOOK_URL` in Phase 4.)

### Timeout
8. **Configuration** → **General configuration** → **Edit** → **Timeout** **0 min
   30 sec** → **Save**.

---

## Step 6 — Permissions for the Enrich Lambda

The Enrich role needs: read `source/`, write `target/`, and consume from SQS. (The
public `dea-lead-owner` lookup is a plain HTTPS GET — no IAM needed.)

1. **Configuration** → **Permissions** → click the **Role name** link (IAM opens).
2. **Add permissions** → **Attach policies** → search **AWSLambdaSQSQueueExecutionRole**
   → check it → **Add permissions**. (This grants `ReceiveMessage`, `DeleteMessage`,
   `GetQueueAttributes` on SQS.)
3. **Add permissions** → **Create inline policy** → **JSON** tab → paste (replace
   `<ACCOUNT_ID>`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSource",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::crm-leads-<ACCOUNT_ID>-us-east-1/source/*"
    },
    {
      "Sid": "WriteTarget",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::crm-leads-<ACCOUNT_ID>-us-east-1/target/*"
    }
  ]
}
```

4. **Next** → name it `crm-enrich-s3` → **Create policy**.

---

## Step 7 — Connect the delay queue to the Enrich Lambda

1. Go to **Lambda** → `crm-enrich-dev` → **Configuration** → **Triggers** → **Add
   trigger** (or use the **+ Add trigger** box on the function diagram).
2. **Source:** **SQS**.
3. **SQS queue:** select `crm-enrich-delay-dev`.
4. **Batch size:** **1**.
5. Leave **Activate trigger** checked. Click **Add**.

Lambda now polls the delay queue; messages become visible 10 minutes after S3
enqueues them, and each one invokes the Enrich function.

---

## Step 8 — Test the full delay + enrich path

1. **Trigger a lead.** Either re-run the Phase 2 test (POST to `/crm`), or upload a
   sample event straight into `source/`:
   - **S3** → bucket → `source/` → **Upload** → add a file named
     `crm_event_lead_TEST123.json` containing:
     ```json
     {"event":{"object_type":"lead","action":"created","lead_id":"lead_TEST123","data":{"display_name":"Test Lead","status_label":"Potential","date_created":"2026-06-05T12:00:00+00:00"}}}
     ```
   > Note: the public `dea-lead-owner` bucket only has real lead files. For
   > `lead_TEST123` the lookup returns **404**, so the Enrich Lambda will raise
   > `LookupNotFound` and (correctly) retry → DLQ. To see a **successful** enrichment,
   > use a real `lead_id` that exists in `dea-lead-owner`.
2. **Wait ~10 minutes** (the delay). You can watch the queue: **SQS** →
   `crm-enrich-delay-dev` → **Monitoring** shows messages in flight.
3. **Check the result:**
   - Success → **S3** → bucket → **`target/`** → `enriched_<lead_id>.json` (contains
     the 7 fields).
   - Lookup 404 / failures → after 3 receives the message lands in
     `crm-enrich-dlq-dev` (check **SQS** → DLQ → **Send and receive messages** →
     **Poll for messages**).
4. **Logs:** **Lambda** → `crm-enrich-dev` → **Monitor** → **View CloudWatch logs**
   — look for `enrich.stored` (success), `enrich.notify_skipped` (no Slack yet, Phase
   4), or a `LookupNotFound` traceback.

---

## What you built (maps to `template.yaml`)

| Console resource | Template resource |
| --- | --- |
| `crm-enrich-dlq-dev` | `DeadLetterQueue` |
| `crm-enrich-delay-dev` (delay 600s, redrive ×3) | `DelayQueue` |
| Queue access policy | `DelayQueuePolicy` |
| S3 event notification on `source/` | `DataBucket.NotificationConfiguration` |
| `crm-enrich-dev` + SQS trigger + IAM | `EnrichFunction` + its event/policies |

**Next:** [phase4-slack.md](phase4-slack.md).
