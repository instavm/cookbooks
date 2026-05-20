# HN Signal Scanner (Recipe #08)

A standalone InstaVM cookbook that scans Hacker News for AI/devtools signal, deduplicates with a persistent volume, filters with an LLM, and emails a digest via Mailtrap.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Persistent volume | `seen_stories.json` survives across runs — no duplicate digests |
| Egress allowlist | Only HN Algolia + Mailtrap SMTP + vault LLM hosts |
| Vault-injected keys | OpenAI/Anthropic keys never in the VM env |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)
- Mailtrap SMTP credentials (or set `MAIL_DRY_RUN=1` for testing)

## Deploy

```bash
cd recipe-08-hn-signal-scanner
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Optional env at deploy:

```bash
instavm deploy . --env DIGEST_TO=you@example.com --env LLM_PROVIDER=openai
```

## Verify

1. Open the share URL → `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — preview digest without LLM or email
3. `POST /run` — full scan (requires vault + Mailtrap)

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```

## Future cron

When `kind: cron` deploy is supported, add a `schedule:` block and point `start_command` at `python agent.py` for one-shot runs.
