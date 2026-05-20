# ABM Daily Monitor (Recipe #14)

Daily Linkup news per target account, fingerprint diff store, Mailtrap digest.

## Deploy

```bash
cd recipe-14-abm-daily-monitor
instavm vault setup .
instavm deploy .
```

## Verify

1. `GET /health`
2. `POST /accounts` with `{"accounts":["acme.com","globex.io"]}`
3. `POST /run?dry_run=1`
