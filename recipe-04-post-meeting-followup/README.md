# Post-Meeting Follow-up (Recipe #04)

A standalone InstaVM cookbook that receives meeting transcripts via webhook, drafts follow-up emails with an LLM, and saves them to `/mnt/data/followups/`.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Webhook-triggered service | Recall.ai or your notetaker POSTs to `/webhook/transcript` |
| Persistent volume | Follow-up drafts saved as JSON under `/mnt/data/followups/` |
| Egress allowlist | Only vault LLM hosts — transcript stays on the VM |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)

## Deploy

```bash
cd recipe-04-post-meeting-followup
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Point your transcript provider at:

```
POST https://<your-share-url>/webhook/transcript
```

## Verify

1. `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — sample transcript without LLM
3. `POST /webhook/transcript?dry_run=1` with transcript JSON

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
