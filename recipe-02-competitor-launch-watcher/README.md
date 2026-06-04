# Competitor Launch Watcher (Recipe #02)

A standalone InstaVM cookbook that fetches competitor blog/changelog pages, diffs titles against a persistent cache, and summarizes new launches with an LLM.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Persistent volume | `competitor_titles.json` stores yesterday's titles for true diffing |
| Egress allowlist | Only competitor domains + vault LLM hosts |
| Vault-injected keys | OpenAI/Anthropic keys never in VM env |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)

## Deploy

```bash
cd recipe-02-competitor-launch-watcher
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Optional env at deploy:

```bash
instavm deploy . --env 'COMPETITOR_URLS=[{"name":"Acme","url":"https://acme.com/blog"}]'
```

## Verify

1. Open the share URL → `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — preview diffs without LLM
3. `POST /run` — full watch (requires vault)

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
