# Podcast Prep Agent (Recipe #17)

`POST /transcript` generates show notes; set `with_tts=true` for Cartesia stub audio metadata.

## Verify

1. `POST /transcript?dry_run=1` with transcript JSON
2. `GET /notes`
