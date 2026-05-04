# InstaVM Cookbooks

A public catalog of apps and experiences you can deploy with `instavm cookbook deploy`.

Each cookbook lives at the repo root:

- `/<slug>/instavm.yaml`
- `/<slug>/Dockerfile`
- `/<slug>/...app files...`

## Local Validation

```bash
python3 scripts/validate_manifests.py
```

## Included Apps

- `hello-fastapi`: a simple FastAPI app with a hello page and health endpoint.
- `neon-city-webgl`: immersive fullscreen WebGL cityscape with procedural towers and a looping robot pedestrian.
- `claude-simple-chatapp`: browser chat for Claude with a React frontend and live conversation threads.
- `openai-agents-js-chat`: streaming browser chat with tool calls, reasoning, and support handoffs.
- `openai-agents-python-research`: newspaper-style deep research desk. The agent searches and reads the public web through a Chromium browser running on InstaVM and files a cited memo; the OpenAI key never enters the deployed VM (consumed from the org vault).
- `openai-agents-python-injection-scanner`: streaming prompt-injection scanner; runs adversarial tooling against an uploaded document inside a fresh, egress-locked InstaVM child sandbox. *First cookbook to use InstaVM as the OpenAI Agents SDK sandbox provider.*
- `openai-agents-python-vibe-preview`: describe a small web app, watch the agent build it inside a fresh InstaVM microVM, and click a live TLS preview URL backed by an InstaVM share.
- `openai-agents-python-vault-demo`: OpenAI Agents SDK on InstaVM with **no real OpenAI key in the orchestrator or in the sandbox**. The cookbook holds only `INSTAVM_API_KEY`; `OPENAI_API_KEY` is a literal placeholder string and the org-scoped InstaVM Vault rewrites it to the real value at TLS write time.
- `vscode-microvm`: VS Code in the browser via `coder/code-server` (Apache-2.0), running inside a Firecracker microVM. Edit code in the browser; everything executes in a real KVM VM with the same isolation, secrets, and audit posture as any other InstaVM workload.
- `google-adk-web-chat`: travel-focused city guide chat for itineraries, neighborhoods, and timing advice.
- `dspy-hosted-chat`: structured DSPy chat that replies with a concise answer and a sharp follow-up question.

## Sandbox-provider cookbooks

`openai-agents-python-injection-scanner` and `openai-agents-python-vibe-preview` are different from every other cookbook in this repo: instead of running the agent loop in the deployed VM and calling OpenAI directly, the deployed FastAPI app uses InstaVM as the OpenAI Agents SDK *sandbox provider*. Every request spawns a fresh, disposable child microVM via `InstaVMSandboxClient` where the agent's shell and file tools run.

```
Browser -> Outer cookbook VM (orchestrator)
              |  holds OPENAI_API_KEY + INSTAVM_API_KEY
              v
           InstaVM control plane
              |
              v
           Fresh disposable child microVM
              - workspace seeded from Manifest
              - egress: package mirrors only
              - no API keys
              - dies at end of run (or after preview TTL)
```

### Security model

- The Agents SDK runs the model **in the orchestrator process**. The child sandbox executes tool calls (shell, files, optional ports) but never sees `OPENAI_API_KEY` or `INSTAVM_API_KEY`.
- Egress in the child sandbox is locked: `allow_internet_access=False`, `allow_http=False`, `allow_https=False`, `allow_package_managers=True`. The agent inside can install packages from PyPI/apt mirrors but cannot reach attacker-controlled URLs.
- A successful prompt injection from a hostile document has nowhere to exfiltrate to: no keys, no internet egress, disposable VM.

### Vault adoption: `openai-agents-python-vault-demo`

`openai-agents-python-vault-demo` is the inverse pattern. The cookbook holds **no** real `OPENAI_API_KEY` anywhere; the orchestrator and the child sandbox both call `api.openai.com` using a literal placeholder string (default: `OPENAI_KEY`). The org-scoped InstaVM Vault — set up once via four CLI commands — substitutes the real credential on the wire at TLS write time.

```mermaid
flowchart LR
  cli["instavm vault create / secret set / service add (one-time)"]
  vault[("Org Vault: OPENAI_KEY<br/>bound to api.openai.com")]
  orch["Orchestrator<br/>OPENAI_API_KEY=OPENAI_KEY<br/>(placeholder)"]
  child["Child sandbox<br/>OPENAI_API_KEY=OPENAI_KEY<br/>(placeholder)"]
  upstream[api.openai.com]

  cli --> vault
  orch --> child
  orch -->|"openai SDK request"| upstream
  child -->|"openai SDK request"| upstream
  vault -.->|"MITM rewrite at egress:<br/>real key on the wire"| upstream
```

Vault is **organization-scoped** — every VM your org launches inherits the bindings. The cookbook never calls a vault API; it only consumes what the user has already set up via CLI. See [openai-agents-python-vault-demo/README.md](openai-agents-python-vault-demo/README.md) for the four commands and a falsifiability check (`echo $OPENAI_API_KEY` inside the cookbook VM should print the placeholder).

## One-time vault setup (covers every cookbook)

The vault pattern isn't limited to `openai-agents-python-vault-demo` and `openai-agents-python-research` — any cookbook that needs `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. can consume them from the same org vault. Set this up **once** and then deploy any cookbook without pasting credentials into a deploy form.

```bash
# 1. Create an org vault. Pick any name; cookbooks scan all org vaults.
VAULT_ID=$(instavm vault create cookbook-org -j \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. Add a credential by name. Use the *placeholder name* the cookbooks
#    expect (OPENAI_KEY for OpenAI, ANTHROPIC_KEY for Anthropic, etc.).
#    The CLI prompts for the value so it never enters your shell history.
instavm vault secret set "$VAULT_ID" OPENAI_KEY

# 3. Bind that credential to a hostname. The egress proxy will substitute
#    the real value on every TLS request to that host.
instavm vault service add "$VAULT_ID" \
  --host api.openai.com --auth-type bearer --credential OPENAI_KEY

# 4. Verify
instavm vault discover "$VAULT_ID"
```

After step 4, deploy any vault-aware cookbook with **only** an `INSTAVM_API_KEY` secret — no `OPENAI_API_KEY` ever appears in the VM:

```bash
cd openai-agents-python-research
instavm deploy .
# CLI prompts for INSTAVM_API_KEY only.
```

Cookbooks that use the vault pattern have a `Vault · …` pill in their UI; if it shows `MISSING`, the homepage prints the four commands above. Adding a new credential (e.g. ANTHROPIC_KEY) is just steps 2 and 3 with the new name and host — no redeploy needed.

## Making existing cookbooks more interesting

Each idea below preserves the standard cookbook contract (no manifest changes), so `instavm cookbook deploy <slug>` and `instavm deploy <local-path>` keep working. The user just supplies an extra `INSTAVM_API_KEY` secret and the chat gains a sandboxed tool call.

- `claude-simple-chatapp`: add a `run_python` tool that materializes the snippet into a Manifest entry and executes it in a per-message InstaVM sandbox; render stdout/stderr/charts inline. Same UI, much more powerful.
- `openai-agents-js-chat`: add a `Run code` button next to assistant messages that contain code blocks; spin up a JS-Agents-SDK sandbox via the InstaVM provider and stream the result.
- `dspy-hosted-chat`: add a self-grader pass that runs the previous answer through a sandbox-executed Python evaluator (e.g., property-based tests) and reports pass/fail before showing the answer.
- `google-adk-web-chat`: add an itinerary validator tool that runs a small Python checker (open hours / transit time feasibility) in a sandbox.
- `openai-agents-python-research`: add an optional `verify_with_code` step that materializes any computed claim into a sandboxed Python check before including it in the briefing.

## Deploy Contract

`instavm.yaml` drives deploy behavior for both `instavm cookbook deploy` and the future `instavm deploy`.

Required top-level keys:

- `schema_version`
- `slug`
- `title`
- `version`
- `summary`
- `category`
- `runtime`
- `deploy`
- `vm`
- `app`
- `run`
- `secrets`
- `post_deploy_notes`

`deploy.kind` supports:

- `published_snapshot`
- `upload_and_run`

Runtime secrets are injected as environment variables at deploy time. They are not stored in this repo.

## Publishing

First-party cookbook images publish to Docker Hub, and the corresponding public system snapshots use deterministic names like `cookbook/<slug>:<version>`.
