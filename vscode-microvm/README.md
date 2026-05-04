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

- code-server **4.96.4**, pinned in two places so snapshot builds match `upload_and_run`:
  - [`instavm.yaml`](instavm.yaml) — `CS_VERSION` inside `setup_command` (tarball install on the VM).
  - [`Dockerfile`](Dockerfile) — `--version 4.96.4` passed to the upstream install script.
- A seeded **`/root/workspace`** tree (when `HOME` is `/root`): files from [`workspace/`](workspace/) are copied to `$HOME/workspace` at setup time (`WELCOME.md`, etc.).
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

Or take the alternate snapshot-based route — build a snapshot from this cookbook's [`Dockerfile`](Dockerfile), boot a VM from it, then share port 8080:

```bash
SNAP_ID=$(instavm snapshot build . \
  --name vscode-microvm-snap --memory 4096 --vcpu 2 -j | jq -r .id)
# Wait until snapshot status is `ready`, then create a VM from it:
instavm create --snapshot "$SNAP_ID" --memory 4096 --vcpu 2
# Note the VM ID from the output, then expose port 8080:
instavm share create "$VM_ID" 8080 --public
```

## Bump or fork

To bump code-server, keep the tarball pin and the Dockerfile pin in sync:

1. Edit **`CS_VERSION`** in [`instavm.yaml`](instavm.yaml) (`setup_command`).
2. Edit **`ARG CS_VERSION`** in [`Dockerfile`](Dockerfile) (passed to `install.sh --version`).

Release assets live at <https://github.com/coder/code-server/releases>.

To swap to [openvscode-server](https://github.com/gitpod-io/openvscode-server) (Gitpod's fork, closer to upstream VS Code) or [agent-infra/sandbox](https://github.com/agent-infra/sandbox) (kitchen-sink: editor + VNC + terminal + MCP), replace the install mechanism and adjust the start command + healthcheck path. openvscode-server uses connection tokens via URL fragments instead of `PASSWORD`, so the auth UX changes.

## Attribution

This cookbook redistributes [`coder/code-server`](https://github.com/coder/code-server) under the Apache-2.0 license. When installed via the upstream Debian packages or tarball, the license ships under paths such as `/usr/lib/code-server/LICENSE.txt` or `/opt/code-server/LICENSE.txt`. All editor functionality is upstream's; this cookbook only adds packaging and InstaVM-specific glue.
