# Investor CRM Updater (Recipe #05)

A standalone InstaVM cookbook that receives email signal webhooks, extracts investor contact fields with an LLM, and upserts records to `/mnt/data/crm.json`.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Always-on listener | Webhook endpoint at `/webhook/email-signal` on your share URL |
| Persistent volume | CRM JSON survives restarts at `/mnt/data/crm.json` |
| Egress allowlist | Only vault LLM hosts — investor emails stay on the VM |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)

## Deploy

```bash
cd recipe-05-investor-crm-updater
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Wire your email automation to:

```
POST https://<your-share-url>/webhook/email-signal
```

## Verify

1. `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — sample email signal without LLM
3. `POST /webhook/email-signal?dry_run=1` with email JSON

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
