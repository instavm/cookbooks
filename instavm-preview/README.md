# InstaVM Preview

Consumer product: describe a small web app → agent builds it in an isolated Firecracker microVM → live HTTPS preview.

## Stack

- **Agent:** OpenAI Agents SDK `SandboxAgent`
- **Isolation:** `InstaVMSandboxClient` child microVM + TLS share on port 8080
- **UI:** polished static shell (no AI-slop copy)
- **Quotas:** guest builds/day, iterates/session, concurrent build cap

## Local run (prod API)

Uses your **prod Pro** InstaVM key from `~/Documents/projects/.instavm` and OpenAI key from `~/Documents/projects/.openai`. The Agents SDK runs the model on your laptop; child microVMs stay on InstaVM.

```bash
cd cookbooks/instavm-preview

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

Open http://127.0.0.1:8000

### Conversation history

Builds are saved in the browser (`localStorage`) as conversations: prompt, phases,
tool steps, preview URL, session id, usage, and TTL. A collapsible left sidebar
lists them (ChatGPT-style). Click to restore the page state; **New build** starts
fresh. Deep-link with `/?c=<conversation_id>`.

```bash
# Account primitives: session + sqlite, volumes upload, SSH hint, DB system prompt
PREVIEW_LOCAL=1 python3 scripts/smoke_primitives.py

# Full Preview SSE build that asks for sqlite under app/data/
python3 scripts/e2e_sqlite_build.py http://127.0.0.1:8000

# Build then follow-up revise (iterate) and assert HTML changed
python3 scripts/e2e_iterate.py http://127.0.0.1:8000
```

Key resolution order:

| Secret | Order |
|---|---|
| `INSTAVM_API_KEY` | env → `~/Documents/projects/.instavm` → `~/.instavm/config.json` |
| `OPENAI_API_KEY` | env → `~/Documents/projects/.openai` → `~/.instavm/secrets/openai` → `./.env` |
| `OPENAI_MODEL` | defaults to **`gpt-5.4-nano`** (override only if you want a heavier plan) |

`PREVIEW_LOCAL=1` (set by `run_local.sh`) enables file-based loading. Deployed cookbooks leave it unset so vault placeholders still work.

Workspace note: prod sandbox VMs run as `appuser`. Preview uses
`PREVIEW_WORKSPACE_ROOT=/home/appuser/workspace` (not `/workspace`, which is not writable).

Local dependency tip (Agents SDK ≥0.18):

```bash
pip install -e ../../sandbox_client   # normalize_path(for_write=…) fix
pip install 'openai-agents>=0.18.3,<0.19'
```

E2E smoke:

```bash
PREVIEW_LOCAL=1 python scripts/e2e_hello_world.py
```


## Deploy

```bash
instavm deploy .
```

## Product routes

| Route | Purpose |
|---|---|
| `GET /` | Consumer UI |
| `GET /api/config` | Signup/billing URLs + PostHog config |
| `GET /api/templates` | Five remixable starters |
| `GET /api/guest` | Guest quota status + cookie |
| `POST /api/build` | SSE build stream (optional `attachments` screenshots) |
| `POST /api/iterate` | SSE iterate on same sandbox (optional screenshots) |
| `GET /api/session/{id}` | Remix lookup |

### LLM metering

OpenAI Agents SDK aggregates usage on `stream.context_wrapper.usage` after each run.
Preview emits an SSE `usage` event with:

```json
{
  "requests": 3,
  "input_tokens": 12400,
  "output_tokens": 2100,
  "total_tokens": 14500,
  "model": "gpt-5.4-nano"
}
```

### Data / databases in the sandbox

Agent instructions default to:

- **sqlite3** (stdlib) for normal apps — DB file under `PREVIEW_DATA_DIR`
  (default `/home/appuser/workspace/app/data`)
- **DuckDB** only for analytics / when asked — same data directory
- No Postgres/MySQL/Mongo unless you later attach managed services

For durable sandboxes with a mounted volume, set `PREVIEW_VOLUME_DATA_DIR` so
DB files land on the volume instead of the ephemeral workspace.

### Screenshot attachments

Attach up to 3 images (png/jpeg/webp/gif, 4MB each) and prompt e.g. “build similar to this”.
The model receives them as vision input; copies are also written under `app/reference/` in the sandbox.

```json
{
  "prompt": "Build similar to this",
  "attachments": [
    {
      "name": "shot.png",
      "mime_type": "image/png",
      "data_base64": "<base64>"
    }
  ]
}
```

## Funnel

1. Guest builds (cookie `ivm_preview_guest`)
2. **Save account** → `INSTAVM_SIGNUP_URL` (default dash signup `?from=preview`)
3. **View plans** → usage/billing on dash
4. Share/remix via `/?remix=<session_id>` and footer link injected into built apps
