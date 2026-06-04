# Cold Outbound Research (Recipe #13)

Prospect research via Exa, LLM-personalized cold email, Mailtrap send with dedup store.

## Deploy

```bash
cd recipe-13-cold-outbound-research
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

## Verify

1. `GET /health`
2. `POST /prospect?dry_run=1` with `{"name":"Pat","email":"pat@acme.com","company":"Acme","domain":"acme.com"}`
