# vscode-microvm

VS Code in the browser, running inside a Firecracker microVM.

This cookbook wraps [`coder/code-server`](https://github.com/coder/code-server) (Apache-2.0) — the same project that powers many "VS Code in browser" experiences — and packages it as a deployable InstaVM cookbook. The user gets a real VS Code editor in their browser; the editor's terminal, file system, and processes all execute inside a real KVM-backed microVM with InstaVM's deny-by-default egress posture.

## Why this matters

Other "VS Code in browser" products (Daytona, Coder, Gitpod) run the editor inside a Docker container that shares the host kernel. This cookbook proves the same UX works on top of a microVM, which buys you:

- Per-tenant kernel isolation (no shared `/proc`, no shared kernel exploits).
- Deny-by-default egress at the platform layer, not at the editor layer.
- The editor inherits the same secrets policy, network policy, and audit trail as any other InstaVM workload.

## Deploy

This is a cookbook (it has an `instavm.yaml`), so `instavm deploy` reads everything it needs — port, healthcheck, start command, secrets — directly from the manifest. From this directory:

```bash
instavm deploy . --yes
```

(Requires `instavm` CLI version with the manifest-aware fast-path; older versions fall through to Python/Node auto-detect and need explicit `--port` / `--start-command` overrides — see "Compatibility" below.)

You will be prompted for one secret:

| Secret | What it does |
| --- | --- |
| `PASSWORD` | The password the editor's login screen will accept. Pick a strong value; the share URL is public by default. |

Once readiness completes, open the share URL InstaVM prints **with a `?folder=/root/workspace` query param**:

```
https://<share-host>.instavm.site/?folder=/root/workspace
```

Enter the `PASSWORD` you supplied at the login screen.

> **Why the query param?** code-server's web build only ships the local `file://` filesystem provider. If you open the bare share URL, code-server constructs the workspace URI as `vscode-remote://<share-host>.instavm.site/workspace` (it uses `window.location.host` as the URI authority) and asks for a "remote" FS provider that doesn't exist in the web build, surfacing the error `File system provider for vscode-remote://… is not available`. Passing `?folder=/root/workspace` overrides that with a plain path which is resolved as `file:///root/workspace` and handled by the local provider. If you previously opened the bare URL and the editor is now stuck on the broken workspace, also clear the share host's localStorage in DevTools (the last-opened workspace URI is persisted there).

## What is shipped inside

- code-server `4.96.4` (bumpable by editing the `FROM` line in [Dockerfile](Dockerfile)).
- A seeded `/workspace/WELCOME.md` orientation file.
- `--auth password`, `--disable-telemetry`, `--disable-update-check` flags so the editor behaves predictably under locked-down egress.

## Auth posture

This cookbook ships with `share_public_default: true`. That means the share URL is **internet-reachable** by anyone who has the link. The editor's built-in password screen is what gates it. Implications:

- Pick a long, unique `PASSWORD` at deploy time. code-server's login screen is unauthenticated below the password layer.
- If you want stricter access control, edit [instavm.yaml](instavm.yaml) and set `share_public_default: false`. Teammates can then be invited via `instavm shares grant <email>` after deploy.
- If you have a vault bound to the org, the orchestrator does not need to handle any user credentials — InstaVM's egress proxy injects them transparently for any HTTPS service the user calls from inside the editor's terminal.

## Compatibility with older `instavm` CLI versions

The CLI's `instavm deploy <path>` command historically only auto-detected Python/Node/Go/Deno/static projects. If your CLI predates the manifest-aware fast-path, run:

```bash
instavm deploy . \
  --port 8080 \
  --health-path /healthz \
  --start-command 'code-server --bind-addr 0.0.0.0:8080 --auth password --disable-telemetry --disable-update-check' \
  --env PASSWORD=YourPassword \
  --yes
```

Note the start command does **not** pass a folder argument — see "Why the query param?" above. Open the share URL with `?folder=/root/workspace`.

Or take the alternate snapshot-based route — bake the upstream image into a private InstaVM snapshot and boot it directly:

```bash
SNAP_ID=$(instavm snapshot build codercom/code-server:4.96.4 \
  --name vscode-microvm-0.1.0 --memory 4096 --vcpu 2 -j | jq -r .id)
# Wait for snapshot status: ready
instavm create --snapshot $SNAP_ID --memory 4096 --vcpu 2
# (note the VM ID, then expose port 8080)
instavm share create $VM_ID 8080 --public
```

The snapshot route bakes `PASSWORD` into the image at build time (via `--env PASSWORD=...`), so each deploy needs its own snapshot. For a per-user cookbook with per-user passwords, the manifest path above is simpler.

## Bump or fork

To bump code-server:

```diff
- FROM codercom/code-server:4.96.4
+ FROM codercom/code-server:4.X.Y
```

Find current tags at <https://hub.docker.com/r/codercom/code-server/tags>.

To swap to [openvscode-server](https://github.com/gitpod-io/openvscode-server) (Gitpod's fork, closer to upstream VS Code) or [agent-infra/sandbox](https://github.com/agent-infra/sandbox) (kitchen-sink: editor + VNC + terminal + MCP), replace the `FROM` line and adjust the start command + healthcheck path. openvscode-server uses connection tokens via URL fragments instead of `PASSWORD`, so the auth UX changes.

## Attribution

This cookbook redistributes [`coder/code-server`](https://github.com/coder/code-server) under the Apache-2.0 license. The full upstream license remains inside the image at `/usr/lib/code-server/LICENSE.txt`. All editor functionality is upstream's; this cookbook only adds packaging and InstaVM-specific glue.
