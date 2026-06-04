# Substack Distribution (Recipe #07)

Substack post rewritten for LinkedIn and X with staged preview.

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Persistent volume | Recipe state survives restarts when configured |
| Egress allowlist | Only required upstream hosts are reachable |
| Vault-injected keys | API keys never stored in VM environment |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to: api.firecrawl.dev, api.openai.com
- For local tests set `ALLOW_LOCAL_SECRETS=1` or use `*_MOCK=1` flags

## Deploy

```bash
cd recipe-07-substack-distribution
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

## Verify

1. Open the share URL → GET /health, POST /publish?dry_run=1, GET /preview
2. Use `?dry_run=1` on POST routes when testing without live sends

## Local tests

```bash
export ALLOW_LOCAL_SECRETS=1
pip install -r requirements.txt
pytest tests/test_unit.py tests/test_smoke.py
```
