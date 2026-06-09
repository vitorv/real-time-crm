# Phase 5 — Close Subscription, End-to-End Validation & Teardown (Console Guide)

**Covers:** registering the real **Close webhook subscription**, validating the whole
pipeline end-to-end, and **tearing everything down** so you don't pay for idle
resources.

**Prerequisites:** Phases 2–4 done; you have the **`Prod/crm` invoke URL** from
Phase 2.

```
Close (new lead) ─▶ /crm ─▶ Ingest ─▶ source/ ─▶ delay 10m ─▶ Enrich ─▶ target/ + Slack
```

---

## Step 1 — Register the Close webhook subscription

Your endpoint must already be live (Phase 2). The Close webhook is what actually
triggers the pipeline from real leads.

1. Confirm your endpoint URL:
   `https://<api-id>.execute-api.us-east-1.amazonaws.com/Prod/crm`
2. **For this project**, per the assignment you don't create the Close subscription
   yourself — **send the URL to Azmat or Ninad** and ask them to create a
   `lead.created` webhook subscription pointing at it. They hold the Close account/API
   access.
3. *(For reference, if you owned the Close account)* you'd create it via the Close API
   (see https://developer.close.com/resources/webhook-subscriptions/), roughly:
   ```bash
   curl -X POST https://api.close.com/api/v1/webhook/ \
     -u "YOUR_CLOSE_API_KEY:" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://<api-id>.execute-api.us-east-1.amazonaws.com/Prod/crm",
          "events":[{"object_type":"lead","action":"created"}]}'
   ```

> Until the subscription exists, the pipeline only runs from manual test events.

---

## Step 2 — End-to-end validation

Do this once the subscription is live (or simulate by POSTing a real lead event).

1. **Create a test lead in Close** (or POST a sample event to `/crm` with a `lead_id`
   that exists in the public `dea-lead-owner` bucket).
2. **Within seconds:** check **S3 → `source/`** for `crm_event_<lead_id>.json`
   (confirms FR1/FR2 / Ingest).
3. **Watch the delay:** **SQS → `crm-enrich-delay-dev` → Monitoring** shows
   "Messages available" / "in flight". Delivery happens ~10 minutes after ingest
   (confirms FR3).
4. **After ~10 minutes:** check **S3 → `target/`** for `enriched_<lead_id>.json`
   (confirms FR4) and your **Slack channel** for the New Lead Alert (confirms FR5).
5. **Trace any issues in CloudWatch:** open **Lambda → (function) → Monitor → View
   CloudWatch logs**. Useful log events: `ingest.stored`, `enrich.stored`,
   `enrich.notified`; failures show `ingest.bad_request`, `LookupNotFound`, or
   `SlackError`.

### Validation checklist
- [ ] Lead lands in `source/` within seconds.
- [ ] Message held ~10 minutes in the delay queue (not processed early).
- [ ] `target/` enriched file matches by `lead_id` (correct owner/email/funnel).
- [ ] Slack alert received with all 7 fields.
- [ ] A bad/unknown lead ends up in the **DLQ**, not lost.

---

## Step 3 — (Optional) Add basic monitoring

To catch failures without watching logs:

1. **SQS → `crm-enrich-dlq-dev` → Monitoring** → the **ApproximateNumberOfMessagesVisible**
   metric. Click the metric → **Actions → Create alarm** → threshold **≥ 1** →
   create an **SNS topic** with your email → **Create alarm**. You'll get an email if
   anything dead-letters.
2. Repeat for the Lambdas' **Errors** metric if desired (**Lambda → function →
   Monitor → Metrics → Errors → Create alarm**).

---

## Step 4 — Teardown (delete everything)

Do this when you're done to avoid charges. Delete in this order (dependencies first):

1. **API Gateway:** API Gateway → **APIs** → select `crm-api` → **Actions** →
   **Delete**.
2. **Lambdas:** Lambda → select `crm-ingest-dev` → **Actions → Delete**; repeat for
   `crm-enrich-dev`. (This also removes their SQS trigger / event source mapping.)
3. **S3 event notification** is removed with the bucket, but the bucket must be
   **emptied** before deletion: S3 → bucket → **Empty** (type to confirm) → then
   **Delete** the bucket.
4. **SQS queues:** SQS → delete `crm-enrich-delay-dev` and `crm-enrich-dlq-dev`.
5. **IAM roles:** IAM → **Roles** → search `crm-ingest-dev` / `crm-enrich-dev` (the
   auto-created execution roles, names start with the function name) → delete each.
   Their inline policies go with them.
6. **CloudWatch log groups** (optional, tiny cost): CloudWatch → **Log groups** →
   delete `/aws/lambda/crm-ingest-dev` and `/aws/lambda/crm-enrich-dev`.
7. **Slack app** (optional): delete the app at https://api.slack.com/apps to revoke
   the webhook.
8. **CloudWatch alarm + SNS topic** (if you made them in Step 3).

> Idle cost is near-zero (no servers), but S3 storage, retained DLQ messages, and
> CloudWatch logs accrue tiny charges over time — teardown keeps the account clean.

---

## The easier way (for next time)

Everything in these four guides is exactly what `template.yaml` provisions in one
command. Once you've done it by hand and understand the pieces:

```powershell
sam build
sam deploy --guided --parameter-overrides SlackWebhookUrl=https://hooks.slack.com/services/XXX/YYY/ZZZ
# teardown:
sam delete
```

That's the same stack, reproducible and version-controlled — the manual console
steps here are for learning what SAM does under the hood.
