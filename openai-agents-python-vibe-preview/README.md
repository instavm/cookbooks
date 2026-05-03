# Vibe Preview

Describe a small web app and watch a sandbox agent build it inside a fresh
**InstaVM microVM**, then click a live TLS preview URL backed by an InstaVM
share.

This cookbook plugs `InstaVMSandboxClient` into `RunConfig(sandbox=...)` and
demonstrates two things container-style sandbox providers can't easily match:

1. **Per-request isolation by VM**, not just process namespaces.
2. **A public TLS preview URL** for the agent's running server, exposed via the
   InstaVM share system &mdash; you click and you're in.

## How it works

```
Browser  -->  Outer cookbook VM (this app)
                  |  holds OPENAI_API_KEY + INSTAVM_API_KEY
                  v
              InstaVM control plane
                  |
                  v
              Fresh child microVM
                  - workspace seeded from Manifest
                  - egress: package mirrors only
                  - exposed port 8080 with TLS share URL
                  - dies after ~15 min
```

`/api/build` does these steps:

1. `client.create(manifest=..., options=InstaVMSandboxClientOptions(exposed_ports=(8080,)))`
2. `sandbox.start()`
3. `Runner.run_streamed(agent, prompt, run_config=RunConfig(sandbox=SandboxRunConfig(session=sandbox)))`
   so the agent uses our pre-created session instead of a throwaway one.
4. Agent scaffolds files under `/workspace/app/` and starts a server on port
   8080 using `python3 -m http.server` (or a custom Python server for dynamic
   apps).
5. `endpoint = await sandbox.resolve_exposed_port(8080)` yields the public TLS
   share URL via `client.shares.create(...)`.
6. The orchestrator schedules a delayed `client.delete(sandbox)` after the TTL
   so previews get cleaned up automatically.

## Security model

- `OPENAI_API_KEY` and `INSTAVM_API_KEY` live **only in the orchestrator
  process**. They are never copied into the child sandbox.
- The Agents SDK runs the model in the orchestrator. The sandbox executes tool
  calls (shell, file writes) without credentials.
- Egress in the child sandbox: `allow_internet_access=False`, `allow_http=False`,
  `allow_https=False`, `allow_package_managers=True`. The agent can `pip
  install` for tooling but cannot reach attacker-controlled URLs.
- Inbound traffic to the preview comes via the InstaVM share proxy, not via
  general internet egress, so locking outbound does not break previews.

## Deploy

```bash
# from the published catalog
instavm cookbook deploy openai-agents-python-vibe-preview

# from a local checkout
cd openai-agents-python-vibe-preview
instavm deploy .
```

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export INSTAVM_API_KEY=instavm_sk_...
uvicorn app:app --reload --port 8000
open http://localhost:8000
```

## Configuration

| Env var                     | Default        | Notes                                                  |
| --------------------------- | -------------- | ------------------------------------------------------ |
| `OPENAI_API_KEY`            | _required_     | Used by the orchestrator only.                         |
| `INSTAVM_API_KEY`           | _required_     | Used by the orchestrator to spawn child sandboxes.     |
| `OPENAI_MODEL`              | `gpt-5.4-nano` | Any chat-completion-capable hosted model.              |
| `VIBE_PREVIEW_TTL_SECONDS`  | `900`          | How long previews stay alive after build.              |
| `VIBE_SANDBOX_MEMORY_MB`    | `2048`         | Memory budget for each child microVM.                  |

## Notes

- The agent is constrained to the Python standard library by default because
  the sandbox has no internet egress. PyPI/apt mirrors are reachable, so it
  can install packages if asked.
- For dynamic apps the agent typically writes a small Python `http.server`
  subclass with hand-rolled routing rather than pulling FastAPI/Flask, since
  that keeps cold start fast and avoids dependency-resolution time.
