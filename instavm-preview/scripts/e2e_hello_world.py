#!/usr/bin/env python3
"""E2E: provision → boot → build hello-world → live preview URL.

Usage (from cookbooks/instavm-preview with venv active):

    PREVIEW_LOCAL=1 python scripts/e2e_hello_world.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PREVIEW_LOCAL", "1")

from app.local_secrets import apply_local_secrets  # noqa: E402

apply_local_secrets(force=True)

from agents import RunConfig, Runner  # noqa: E402
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig  # noqa: E402
from agents.sandbox.entries import File  # noqa: E402
from instavm.integrations.openai_agents import (  # noqa: E402
    InstaVMSandboxClient,
    InstaVMSandboxClientOptions,
)

from app import config  # noqa: E402
from app.build import builder_instructions, _preview_url  # noqa: E402


PROMPT = (
    "Create a Hello World page with polished CSS: large centered heading "
    "'Hello, InstaVM', a short subtitle, a teal accent button that does nothing, "
    "and a soft paper background. Static HTML/CSS only."
)


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "instavm-preview-e2e"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body


async def main() -> int:
    if not os.environ.get("INSTAVM_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        print("Missing keys after local secret load", file=sys.stderr)
        return 1

    print("workspace_root", config.WORKSPACE_ROOT)
    client = InstaVMSandboxClient(api_key=os.environ["INSTAVM_API_KEY"])
    manifest = Manifest(
        root=config.WORKSPACE_ROOT,
        entries={
            "app/.keep": File(content=b""),
            "app/public/.keep": File(content=b""),
        },
    )
    session_id = "e2e-hello"

    print("1) create sandbox…")
    sandbox = await client.create(
        manifest=manifest,
        options=InstaVMSandboxClientOptions(
            memory_mb=config.SANDBOX_MEMORY_MB,
            cpu_count=2,
            timeout=config.SANDBOX_TIMEOUT,
            exposed_ports=(config.PREVIEW_PORT,),
            allow_internet_access=False,
            allow_http=False,
            allow_https=False,
            allow_package_managers=True,
        ),
    )
    print("2) start (mkdir workspace + hydrate)…")
    await sandbox.start()
    print("3) agent build hello world…")
    agent = SandboxAgent(
        name="Preview Builder",
        model=config.MODEL_NAME,
        instructions=builder_instructions(session_id),
        default_manifest=manifest,
    )
    result = await Runner.run(
        agent,
        f"Build the following app and start serving it on port 8080:\n\n{PROMPT}",
        run_config=RunConfig(
            sandbox=SandboxRunConfig(session=sandbox),
            workflow_name="instavm-preview-e2e",
        ),
        max_turns=24,
    )
    print("agent_final", (result.final_output or "")[:400])

    print("4) resolve share URL…")
    endpoint = await sandbox.resolve_exposed_port(config.PREVIEW_PORT)
    url = _preview_url(endpoint)
    print("preview_url", url)

    print("5) HTTP GET preview…")
    try:
        status, body = fetch(url)
    except urllib.error.URLError as exc:
        print("FETCH_FAIL", exc, file=sys.stderr)
        await client.delete(sandbox)
        return 1

    print("http_status", status)
    lower = body.lower()
    ok_hello = "hello" in lower
    ok_css = "<style" in lower or "stylesheet" in lower or "background" in lower
    ok_footer = "instavm preview" in lower
    print("checks", {"hello": ok_hello, "css": ok_css, "footer": ok_footer})

    print("6) cleanup…")
    await client.delete(sandbox)

    if status != 200 or not ok_hello or not ok_css:
        print("E2E_FAIL", file=sys.stderr)
        return 1
    print("E2E_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
