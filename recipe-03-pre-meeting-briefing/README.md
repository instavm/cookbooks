# Pre-Meeting Briefing (Recipe #03)

A standalone InstaVM cookbook that receives Cal.com booking webhooks, researches attendees via Exa, and returns a markdown pre-meeting briefing.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Webhook-triggered service | Cal.com POSTs to `/webhook/cal` on your share URL |
| Persistent volume | Briefings saved under `/mnt/data/briefings/` |
| Egress allowlist | Only Exa + vault LLM hosts |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Exa API key (vault host `api.exa.ai`)
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)
- Cal.com webhook pointed at your share URL

## Deploy

```bash
cd recipe-03-pre-meeting-briefing
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Register the webhook in Cal.com:

```
POST https://<your-share-url>/webhook/cal
```

## Verify

1. `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — sample attendee briefing without LLM
3. `POST /webhook/cal?dry_run=1` with Cal.com JSON payload

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
