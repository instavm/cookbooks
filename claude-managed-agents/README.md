# Claude Managed Agents — Self-Hosted Sandbox on InstaVM

Self-host the **Claude Managed Agents (CMA)** sandbox execution layer on
[InstaVM](https://instavm.io). Anthropic runs the agent loop; every tool call the
agent makes runs inside an isolated, per-session InstaVM microVM.

The differentiator: **no naked secrets**. The worker microVM — where the
untrusted agent code executes — never receives a real provider credential. The
Anthropic environment key (and any third-party API keys the agent needs) are
injected at the **egress boundary** from the InstaVM **org vault** at TLS write
time. The VM only ever holds placeholder strings.

| | E2B | Blaxel | **InstaVM (this cookbook)** |
|---|---|---|---|
| Tool execution | Worker sandbox | Worker sandbox | Worker microVM |
| Provider secret in worker | **Plaintext file** in sandbox | Proxy-injected | **Vault-injected at egress** |
| Agent sees real key | Yes (on disk) | No | **No** |

## Architecture

```
Anthropic CMA ──(session.status_run_started webhook)──▶ Orchestrator (this app)
control plane                                            FastAPI on an InstaVM
   ▲                                                     service with a public
   │ claim work / post results                          share URL
   │                                                        │ spawns per session
   │                                                        ▼
   └────────────── ant beta:worker poll ◀──────────── Worker microVM
                   (placeholder creds; real keys      egress allowlist +
                    injected at egress from vault)     org-vault injection
```

- The **orchestrator** is a long-lived InstaVM service. Its public share URL
  `/webhook` is registered with Anthropic. It verifies the webhook signature and,
  on `session.status_run_started`, schedules a background dispatch.
- Each session gets a fresh **worker microVM** that runs
  `ant beta:worker poll --workdir /workspace`. The poller claims the session's
  queued work, downloads skills, executes the agent's bash/file tools, posts
  results back, and exits after `--max-idle`.
- The worker's outbound HTTPS to `api.anthropic.com` is restricted by an egress
  allowlist, and the real Anthropic environment key is injected from the bound
  org vault — never stored in the VM.

## Files

| Path | Purpose |
|------|---------|
| `app.py` | FastAPI app: `/`, `/health`, `/webhook`, `/workers`. |
| `orchestrator/config.py` | Worker/dispatcher settings from the environment. |
| `orchestrator/signature.py` | Anthropic webhook verification (SDK `unwrap()` + Standard Webhooks fallback). |
| `orchestrator/worker_pool.py` | Spawns and tracks per-session worker microVMs. |
| `orchestrator/dispatcher.py` | Debounced background dispatch. |
| `lib/secrets.py` | Vault placeholder resolution (no naked secrets). |

## Deploy

```bash
# 1. One-time: bind the org vault so workers get the real Anthropic key at egress.
#    auth_type=api_key, header x-api-key, credential named ANTHROPIC_KEY,
#    mapped to host api.anthropic.com.
instavm vault setup .

# 2. Deploy the orchestrator. The CLI prompts for the deploy-time secrets
#    (webhook signing key, environment id, InstaVM API key).
instavm deploy .

# 3. Confirm it's live and grab the webhook URL.
curl https://<share-url>/health
echo "Register https://<share-url>/webhook in the Claude Console"
```

### Register the webhook

In the [Claude Console](https://platform.claude.com/settings/workspaces/default/webhooks):

1. **Manage → Webhooks → Add endpoint** → URL = `https://<share-url>/webhook`.
2. Subscribe to **only** `session.status_run_started`.
3. Copy the `whsec_...` signing key and re-deploy (or set
   `ANTHROPIC_WEBHOOK_SIGNING_KEY`) so the orchestrator can verify deliveries.

### Create the self-hosted environment + agent

```bash
ant beta:environments create --name "instavm" --config '{"type": "self_hosted"}'
# Open the environment in the Console → Generate environment key.
# Set ANTHROPIC_ENVIRONMENT_ID (deploy prompt); the worker injects the key at egress.

ant beta:agents create <<'YAML'
name: InstaVM Assistant
model: claude-sonnet-4-6
system: You are a helpful assistant.
tools:
  - type: agent_toolset_20260401
YAML
```

Create a session against that agent + environment in the Console and send a
message — Anthropic fires the webhook, the orchestrator spawns a worker microVM,
and `GET /workers` shows it running.

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_WEBHOOK_SIGNING_KEY` | — | `whsec_` key used to verify deliveries (required). |
| `ANTHROPIC_ENVIRONMENT_ID` | — | Self-hosted environment id (required). |
| `ANTHROPIC_ENVIRONMENT_KEY` | placeholder | Real key injected at egress; set only for local dev. |
| `INSTAVM_API_KEY` | vault | API key used to spawn worker microVMs. |
| `WORKER_WORKDIR` | `/workspace` | Worker working directory. |
| `WORKER_MAX_IDLE` | `30s` | Idle timeout before a worker exits. |
| `WORKER_MEMORY_MB` / `WORKER_VCPU` | `2048` / `2` | Worker microVM size. |
| `WORKER_EGRESS_DOMAINS` | — | Extra comma-separated egress hosts for the agent. |
| `ANT_VERSION` | `1.12.0` | `ant` CLI version installed in the worker. |
| `WEBHOOK_VERIFY` | `1` | Set `0` to skip verification (local dev only). |

## Test

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest
```

The suite is fully offline: webhook signing is exercised with a local HMAC, and
worker spawning uses a fake InstaVM client that asserts the worker only ever
receives placeholder credentials.

## Notes

- Anthropic owns the agent loop and reasoning. This cookbook only provides the
  sandbox execution layer (filesystem, tools, network, logs).
- For faster cold starts, bake a worker snapshot with `ant` pre-installed and
  point the worker at it instead of installing `ant` at boot.
- To give the agent third-party API access, add the host to `WORKER_EGRESS_DOMAINS`
  and bind a vault credential for it — keeping the no-naked-secrets guarantee.
