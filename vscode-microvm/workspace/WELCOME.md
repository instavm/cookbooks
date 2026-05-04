# Welcome to VS Code in a Microvm

You are looking at a real Visual Studio Code editor (via [code-server](https://github.com/coder/code-server), Apache-2.0) running inside a Firecracker microVM provisioned by InstaVM.

## What is different from "VS Code in Docker"

Most "VS Code in browser" demos run inside a Docker container that shares the host kernel. This cookbook runs inside a **KVM-backed microVM** with its own kernel, its own network namespace, and InstaVM's deny-by-default egress controls. The editor and your shell get the same isolation guarantees as the rest of the InstaVM platform.

## Try it

1. Press `` Ctrl+` `` (or `Cmd+J` on macOS) to open the integrated terminal.
2. Run `whoami` and `uname -a` to confirm you are inside a Linux microVM.
3. Try `pip install requests` — package mirrors are reachable by default.
4. Try `curl https://example.com` — depending on how your admin configured egress, this may be denied.

## What you cannot do

- The editor is **not persistent across redeployments**. Anything you change under `/workspace` lives only as long as this microVM. Use a persistent volume or `git push` to keep work.
- The InstaVM API key is **not** present in this VM. The orchestrator is what spawned us; we never see its credentials.

## Useful commands

```bash
# What VM am I in?
cat /etc/os-release

# How much memory and CPU?
free -h
nproc

# What ports am I listening on?
ss -tlnp
```

Happy hacking.
