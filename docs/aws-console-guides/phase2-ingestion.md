# Phase 2 — Webhook Ingestion (Console Guide)

**Builds:** an S3 data bucket, the **Ingest** Lambda, and an API Gateway endpoint
(`POST /crm`) that receives the Close webhook and writes
`crm_event_{lead_id}.json` into `s3://…/source/`.

**Covers:** FR1 (receive webhook) + FR2 (store raw event in S3).

**Prerequisites:** read [README.md](README.md), be in **us-east-1**, and build
`lambda_package.zip` (see the README "Package the Lambda code" section).

```
Close webhook ─▶ API Gateway (POST /crm) ─▶ Ingest Lambda ─▶ S3 source/
```

---

## Step 1 — Create the S3 data bucket

1. In the console search bar, type **S3** and open the **S3** service.
2. Click the orange **Create bucket** button.
3. **Bucket name:** `crm-leads-<ACCOUNT_ID>-us-east-1` (must be globally unique —
   that's why we add your account ID).
4. **AWS Region:** confirm **US East (N. Virginia) us-east-1**.
5. **Object Ownership:** leave **ACLs disabled (recommended)**.
6. **Block Public Access:** leave **Block *all* public access** ✅ checked (this is
   private data).
7. **Bucket Versioning:** Disable (default).
8. **Default encryption:** leave **Server-side encryption with Amazon S3 managed
   keys (SSE-S3)** selected.
9. Click **Create bucket**.

You don't need to pre-create the `source/` folder — the Lambda creates objects
under that prefix automatically.

---

## Step 2 — Create the Ingest Lambda

1. In the console search bar, type **Lambda** and open it.
2. Click **Create function**.
3. Select **Author from scratch**.
4. **Function name:** `crm-ingest-dev`.
5. **Runtime:** **Python 3.11**.
6. **Architecture:** **x86_64**.
7. Expand **Change default execution role** → leave **Create a new role with basic
   Lambda permissions** selected (we'll add S3 permissions in Step 4).
8. Click **Create function**.

### Upload the code
9. On the function page, find the **Code** tab → **Code source** panel.
10. Click **Upload from** (top-right of the code panel) → **.zip file**.
11. Click **Upload**, choose your **`lambda_package.zip`**, then **Save**.

### Set the handler
12. Scroll to **Runtime settings** (just below the code) → **Edit**.
13. Set **Handler** to `ingest.app.lambda_handler`.
14. Click **Save**.

### Set environment variables
15. Go to the **Configuration** tab → **Environment variables** → **Edit** → **Add
    environment variable** for each:

| Key | Value |
| --- | --- |
| `DATA_BUCKET` | `crm-leads-<ACCOUNT_ID>-us-east-1` |
| `SOURCE_PREFIX` | `source/` |
| `LOG_LEVEL` | `INFO` |

16. Click **Save**.

### Set the timeout
17. **Configuration** tab → **General configuration** → **Edit** → set **Timeout**
    to **0 min 30 sec** → **Save**.

---

## Step 3 — Give the Lambda permission to write to S3

1. **Configuration** tab → **Permissions**.
2. Under **Execution role**, click the **Role name** link (opens the IAM role in a
   new tab).
3. On the IAM role page, click **Add permissions** → **Create inline policy**.
4. Click the **JSON** tab and paste (replace `<ACCOUNT_ID>`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::crm-leads-<ACCOUNT_ID>-us-east-1/source/*"
    }
  ]
}
```

5. Click **Next**, name it `crm-ingest-s3-write`, and click **Create policy**.

> The basic execution role already allows writing CloudWatch logs; this inline
> policy adds the S3 write. (`sam deploy` would attach an equivalent `S3CrudPolicy`.)

---

## Step 4 — Create the API Gateway endpoint

1. In the console search bar, type **API Gateway** and open it.
2. Find **REST API** (the plain one, *not* "REST API Private" or "HTTP API") and
   click **Build**.
3. Choose **New API**. **API name:** `crm-api`. **Endpoint Type:** Regional.
   Click **Create API**.

### Create the /crm resource
4. In the left panel you're on **Resources**. Click **Create resource**.
5. **Resource name:** `crm` (the path becomes `/crm`). Click **Create resource**.

### Create the POST method
6. With **/crm** selected, click **Create method**.
7. **Method type:** **POST**.
8. **Integration type:** **Lambda function**.
9. Toggle **Lambda proxy integration** **ON** (important — this passes the raw
   request, including `body`, to your handler).
10. **Lambda function:** start typing `crm-ingest-dev` and select it (region must be
    us-east-1).
11. Click **Create method**. When prompted to give API Gateway permission to invoke
    the Lambda, accept (**OK**).

### Deploy the API
12. Click **Deploy API** (top-right).
13. **Stage:** **New stage**. **Stage name:** `Prod`. Click **Deploy**.
14. You'll land on the **Stages** page. Copy the **Invoke URL** at the top — it looks
    like `https://abc123.execute-api.us-east-1.amazonaws.com/Prod`.
15. Your webhook endpoint is that URL **+ `/crm`**:
    `https://abc123.execute-api.us-east-1.amazonaws.com/Prod/crm`

Keep this URL — it's what Close (or you, for testing) will POST to, and what
Phase 5 registers as the Close subscription.

---

## Step 5 — Test it

### Option A — from the API Gateway console
1. Back in **API Gateway** → your API → **Resources** → select the **POST** under
   `/crm` → **Test** tab.
2. In **Request body**, paste a sample Close event (the inner webhook payload):

```json
{
  "event": {
    "object_type": "lead",
    "action": "created",
    "lead_id": "lead_TEST123",
    "data": { "display_name": "Test Lead", "status_label": "Potential", "date_created": "2026-06-05T12:00:00+00:00" }
  }
}
```

3. Click **Test**. You should see **Status: 200** and a body like
   `{"status": "ok", "lead_id": "lead_TEST123", "key": "source/crm_event_lead_TEST123.json"}`.

### Option B — from your terminal (PowerShell)
```powershell
$body = '{"event":{"object_type":"lead","action":"created","lead_id":"lead_TEST123","data":{"display_name":"Test Lead","status_label":"Potential","date_created":"2026-06-05T12:00:00+00:00"}}}'
Invoke-RestMethod -Method Post -Uri "https://abc123.execute-api.us-east-1.amazonaws.com/Prod/crm" -ContentType "application/json" -Body $body
```

### Confirm the object landed
3. Open **S3** → your bucket → you should see a **`source/`** folder containing
   **`crm_event_lead_TEST123.json`**. Click it → **Open** to view the stored event.

### If something's wrong
- Open **Lambda** → `crm-ingest-dev` → **Monitor** tab → **View CloudWatch logs**.
  Each invocation logs a JSON line (`ingest.stored`, `ingest.skipped`, or
  `ingest.bad_request` with the error).
- `AccessDenied` writing to S3 → re-check the inline policy ARN in Step 3.
- 500 / "no module named" → the zip layout is wrong; rebuild with the Python
  command from the README (not `Compress-Archive`).

---

## What you built (maps to `template.yaml`)

| Console resource | Template resource |
| --- | --- |
| S3 bucket | `DataBucket` |
| `crm-ingest-dev` + inline policy | `IngestFunction` + `S3CrudPolicy` |
| `crm-api` REST API, `/crm` POST, `Prod` stage | `ServerlessRestApi` (the `Api` event) |

**Next:** [phase3-delay-enrichment.md](phase3-delay-enrichment.md).
