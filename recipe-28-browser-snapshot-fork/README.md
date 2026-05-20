# Recipe 28 — Browser Snapshot Fork

Showcase cookbook: the orchestrator uses `InstaVMSandboxClient` (OpenAI Agents SDK sandbox provider) to fan out **two parallel child sandboxes** from an optional snapshot, each running a simple `echo` task.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + InstaVM key presence |
| POST | `/fork` | Spawn parallel child sandboxes |

```json
POST /fork
{
  "tasks": ["fork-alpha", "fork-beta"],
  "snapshot_id": "optional-post-login-snapshot-id"
}
```

## Secrets

- `INSTAVM_API_KEY` — required for live forks (injected via InstaVM secret store on deploy).

## Local test

```bash
cd recipe-28-browser-snapshot-fork
pip install -r requirements.txt
pytest -q
```

Unit tests mock `InstaVMSandboxClient`; no live InstaVM calls in CI.

## Deploy

```bash
instavm deploy .
```

See the [InstaVM cookbook](https://instavm.io) recipe 28 for the full browser-use + volume snapshot workflow; this repo ships a minimal fork demo.
