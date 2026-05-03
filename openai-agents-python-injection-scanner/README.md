# Injection Scanner

Streaming prompt-injection scanner. Drop a Markdown / HTML / JSON / text file
and watch a sandbox agent run adversarial tooling against it in real time.

This is one of the first cookbooks that uses **InstaVM as the OpenAI Agents SDK
sandbox provider**. The orchestrator runs the LLM; every scan executes its
shell and Python tools inside a fresh, disposable InstaVM microVM.

## Why this is different

The existing `openai-agents-python-research` cookbook deploys a FastAPI app and
calls `Runner.run(Agent(...), ...)` directly. The agent never gets a sandbox.

This cookbook plugs `InstaVMSandboxClient` into `RunConfig(sandbox=...)`, so
each `/api/scan` request:

1. Materializes the user's untrusted input as `/workspace/input.bin` inside a
   fresh microVM via `Manifest(entries={...})`.
2. Lets the `SandboxAgent` run shell + Python tools to detect prompt-injection
   payloads (instruction overrides, hidden unicode, encoded blobs, link traps,
   embedded HTML/MD trickery).
3. Streams every tool call back to the browser as Server-Sent Events.
4. Reads the agent's final JSON verdict and renders it as a risk card.
5. Destroys the microVM.

## Security model

- `OPENAI_API_KEY` and `INSTAVM_API_KEY` live **only in the orchestrator
  process**. They are never copied into the child sandbox.
- The Agents SDK runs the model in the orchestrator. The sandbox session only
  executes tool calls (shell, files). The agent inside the sandbox has no
  credentials.
- Egress in the child sandbox: `allow_internet_access=False`, `allow_http=False`,
  `allow_https=False`, `allow_package_managers=True`. The agent can `pip install`
  for tooling but cannot reach attacker-controlled URLs.
- A successful prompt injection has nowhere to exfiltrate to: no keys, no
  internet egress, disposable VM destroyed at end of run.

## Deploy

This cookbook follows the standard contract, so all three deploy paths work:

```bash
# from the published catalog (after this PR is merged + catalog refreshes)
instavm cookbook deploy openai-agents-python-injection-scanner

# from a local checkout
cd openai-agents-python-injection-scanner
instavm deploy .

# non-interactive (e.g. CI)
INSTAVM_API_KEY=... OPENAI_API_KEY=... instavm deploy . --yes \\
  --env OPENAI_API_KEY=$OPENAI_API_KEY --env INSTAVM_API_KEY=$INSTAVM_API_KEY
```

The deployed orchestrator calls back to `api.instavm.io` to spawn child
sandboxes per request, using the `INSTAVM_API_KEY` you supplied as a secret.

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

| Env var                       | Default        | Notes                                                |
| ----------------------------- | -------------- | ---------------------------------------------------- |
| `OPENAI_API_KEY`              | _required_     | Used by the orchestrator only.                       |
| `INSTAVM_API_KEY`             | _required_     | Used by the orchestrator to spawn child sandboxes.   |
| `OPENAI_MODEL`                | `gpt-5.4-nano` | Any chat-completion-capable hosted model.            |
| `INJECTION_MAX_BYTES`         | `262144`       | Upload size cap (bytes).                             |
| `INJECTION_SANDBOX_MEMORY_MB` | `1024`         | Memory budget for each child microVM.                |
| `INJECTION_SANDBOX_TIMEOUT`   | `240`          | Per-scan wall-clock timeout (seconds).               |

## What gets sent to the model

The orchestrator only sends the model:

1. The system instructions (the scanner procedure).
2. The agent's tool inputs and outputs (so the model can reason about the next
   step).

The user's raw document content reaches the model only when the agent
explicitly reads it in a tool call &mdash; you can see every read in the live
timeline.
