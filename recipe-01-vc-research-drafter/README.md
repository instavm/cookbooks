# VC Research Drafter (Recipe #01)

A standalone InstaVM cookbook that searches Exa for fresh VC activity, deduplicates against a persistent contact list, drafts warm-intro emails with an LLM, and sends them via Mailtrap.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Persistent volume | `contacted_vcs.json` survives across nightly runs — no duplicate outreach |
| Egress allowlist | Only Exa + Mailtrap SMTP + vault LLM hosts |
| Vault-injected keys | Exa and OpenAI/Anthropic keys never in VM env |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Exa API key (vault host `api.exa.ai`)
- Org vault bound to `api.openai.com` (and optionally `api.anthropic.com`)
- Mailtrap SMTP credentials (or set `MAIL_DRY_RUN=1` for testing)

## Deploy

```bash
cd recipe-01-vc-research-drafter
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

Optional env at deploy:

```bash
instavm deploy . --env DRAFT_TO=you@example.com --env VC_THESIS="AI infrastructure"
```

## Verify

1. Open the share URL → `GET /health` returns `ok: true`
2. `POST /run?dry_run=1` — preview drafts without LLM or email
3. `POST /run` — full run (requires vault + Mailtrap)

## Local tests

```bash
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
