# Recipe 31 — Deterministic Replay

Uses `instavm.cassette_replay.CassetteReplayClient` with a checked-in **`fixtures/cassette.jsonl`** tape. `POST /replay` returns a deterministic LLM response (`REPLAY_OK`) with no network call when the request fingerprint matches.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| POST | `/replay` | Replay chat completion from cassette |

## Cassette layout

- `fixtures/cassette.jsonl` — human-readable tape (checked in)
- `fixtures/recipe31/llm_call.jsonl` — SDK tape path (synced automatically)

## Local test

```bash
cd recipe-31-deterministic-replay
pip install -r requirements.txt
pytest -q
```
