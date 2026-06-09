# Phase 4 — Slack Notification (Console Guide)

**Builds:** a **Slack incoming webhook**, and adds its URL to the Enrich Lambda so it
posts a **New Lead Alert** after writing `target/`.

**Covers:** FR5 (notify the team with the 7 fields).

**Prerequisites:** finish [phase3-delay-enrichment.md](phase3-delay-enrichment.md).
You'll need permission to add an app to a Slack workspace.

```
Enrich Lambda ─(after target/ write)─▶ Slack Incoming Webhook ─▶ #channel
```

---

## Step 1 — Create a Slack incoming webhook (Slack side)

1. Go to **https://api.slack.com/apps** and sign in to your workspace.
2. Click **Create New App** → **From scratch**.
3. **App Name:** `CRM Lead Alerts`. **Pick a workspace:** choose yours. Click
   **Create App**.
4. In the left sidebar under **Features**, click **Incoming Webhooks**.
5. Toggle **Activate Incoming Webhooks** to **On**.
6. Scroll down and click **Add New Webhook to Workspace**.
7. **Choose a channel** to post to (e.g. `#leads` or a test channel) → **Allow**.
8. Back on the Incoming Webhooks page, copy the **Webhook URL**. Its shape is:
   `https://hooks.slack.com/services/<workspace-id>/<channel-id>/<secret-token>`

> Treat this URL as a **secret** — anyone with it can post to your channel. Don't
> commit it to git or paste it in screenshots.

### (Optional) quick sanity check
```powershell
$u = "https://hooks.slack.com/services/<workspace-id>/<channel-id>/<secret-token>"
Invoke-RestMethod -Method Post -Uri $u -ContentType "application/json" -Body '{"text":"hello from CRM test"}'
```
You should see `hello from CRM test` appear in the channel (and the call returns `ok`).

---

## Step 2 — Add the webhook URL to the Enrich Lambda

1. Open **Lambda** → `crm-enrich-dev` → **Configuration** → **Environment variables**
   → **Edit**.
2. Click **Add environment variable**:

| Key | Value |
| --- | --- |
| `SLACK_WEBHOOK_URL` | *(paste your Slack webhook URL)* |

3. Click **Save**.

That's the only change — the Enrich code already calls Slack after the `target/`
write when this variable is set. If it's empty, it logs `enrich.notify_skipped` and
sends nothing (which is why Phase 3 was silent).

> **More secure option (optional):** instead of a plain env var, store the URL in
> **AWS Secrets Manager** and read it in the Lambda. The env-var approach is simplest
> and fine for a learning project; Secrets Manager avoids showing the URL in the
> Lambda console.

---

## Step 3 — Test the notification

1. Trigger a lead that **exists** in the public `dea-lead-owner` bucket (so the
   lookup succeeds) — e.g. re-POST to `/crm` (Phase 2) with a real `lead_id`, or
   drop its `crm_event_<lead_id>.json` into `source/`.
2. Wait the ~10-minute delay.
3. Watch your Slack channel — a **New Lead Alert** should appear with:

   ```
   New Lead Alert
   Name: …          Lead ID: …       Created Date: …    Label: …
   Email: …         Lead Owner: …    Funnel: …
   ```

4. Confirm in **CloudWatch logs** (`crm-enrich-dev` → Monitor → View logs): you
   should see `enrich.stored` followed by `enrich.notified`.

### If the alert doesn't arrive
- `enrich.notify_skipped` in the logs → `SLACK_WEBHOOK_URL` isn't set/saved.
- A `SlackError` in the logs → the webhook URL is wrong/revoked, or Slack returned a
  non-`ok` body. The message will retry (and eventually dead-letter) because a failed
  notify is treated as a failed message on purpose.
- No log at all → the enrichment didn't run; revisit Phase 3 (the lookup may have
  404'd, sending the message to the DLQ).

---

## What you built (maps to `template.yaml`)

| Console action | Template equivalent |
| --- | --- |
| Slack incoming webhook | (external — created in Slack) |
| `SLACK_WEBHOOK_URL` env var on Enrich | `SlackWebhookUrl` `NoEcho` parameter → Enrich `Environment` |

**Next:** [phase5-validation.md](phase5-validation.md).
