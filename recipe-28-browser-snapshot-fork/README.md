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

## Security note on the shell exec inside child sandboxes

`lib/sandbox_fork.py` runs:

```python
result = await session.exec("sh", "-c", f"echo sandbox:{task}")
```

That f-string interpolates the caller-supplied `task` into a shell command. **This is safe here, and only here**, because it runs inside a freshly spawned InstaVM child sandbox with `allow_internet_access=False` and a one-shot lifecycle. The blast radius is the disposable child VM; the parent process and host machine are unreachable.

Do not lift this pattern into code that runs outside the sandbox. If you adapt this recipe and start passing `task` to a subprocess on the orchestrator host, use a list argv form (`subprocess.run(["echo", "sandbox:" + task])`) and treat the input as untrusted. Shell interpolation outside the sandbox is a remote-code-execution vector.
