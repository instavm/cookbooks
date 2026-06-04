# Lost Deal Post-Mortem (Recipe #15)

Upload a sales transcript; get structured post-mortem JSON from the LLM.

## Verify

1. `GET /health`
2. `POST /transcript?dry_run=1` with `{"transcript":"...","deal_name":"Acme"}`
