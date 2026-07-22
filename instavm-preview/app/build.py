"""Build and iterate streams using OpenAI Agents SDK + InstaVMSandboxClient."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

from agents import RunConfig, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.entries import File

from instavm.integrations.openai_agents import (
    InstaVMSandboxClient,
    InstaVMSandboxClientOptions,
)

from . import config
from .attachments import Attachment, agent_input, reference_paths
from .plan import normalize_plan, plan_as_instructions
from .sessions import PreviewSession, store

logger = logging.getLogger("instavm_preview.build")

_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,253}$")
_TODO_DONE_RE = re.compile(r"\[\[todo:done:([a-zA-Z0-9_]{1,32})\]\]")


def looks_like_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return any(
        marker in normalized
        for marker in (
            "dummy",
            "test",
            "placeholder",
            "your_key",
            "your-api-key",
            "changeme",
            "example",
        )
    )


def validate_keys() -> tuple[str, str]:
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    instavm_key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if not openai_key or looks_like_placeholder_secret(openai_key):
        raise RuntimeError("OPENAI_API_KEY is missing or invalid.")
    if not instavm_key or looks_like_placeholder_secret(instavm_key):
        raise RuntimeError("INSTAVM_API_KEY is missing or invalid.")
    return openai_key, instavm_key


def remix_url_for_session(session_id: str) -> str:
    origin = config.PUBLIC_ORIGIN or ""
    path = f"/?remix={quote(session_id)}"
    return f"{origin}{path}" if origin else path


def data_guidance() -> str:
    """Tell the agent which DBs / paths to use inside the sandbox."""
    root = config.WORKSPACE_ROOT
    data = config.VOLUME_DATA_DIR or config.DATA_DIR
    on_volume = bool(config.VOLUME_DATA_DIR)
    where = (
        f"a mounted volume at {data}"
        if on_volume
        else f"{data} under the workspace (session-scoped; survives iterate, not remix)"
    )
    return (
        "\nData & databases:\n"
        "- If the user asks for a database, persistence, CRM, todos, analytics, "
        "or anything stateful, do NOT invent Postgres/MySQL/Mongo/Redis or cloud DBs.\n"
        "- Default: Python `sqlite3` (stdlib). Store the `.db` file on "
        f"{where}. Create the directory with mkdir -p if needed.\n"
        "- Use DuckDB (`pip install duckdb`) only when the user needs analytics, "
        "Parquet/CSV OLAP, or explicitly asks for DuckDB. Keep the DuckDB file on "
        f"the same data path ({data}).\n"
        "- Prefer a small Python HTTP app (stdlib `http.server` + handlers, or a "
        "tiny WSGI-less script) that opens sqlite/duckdb on each request or keeps "
        f"one connection. Put schema init in {root}/app/ and the DB file under "
        f"{data}/ — never under public/.\n"
        "- JSON/CSV files under the data dir are fine for tiny apps; upgrade to "
        "sqlite when they ask for search, relations, or multi-user edits.\n"
        "- Do not require Docker, apt postgres, or external DB services.\n"
    )


def builder_instructions(
    session_id: str,
    has_attachments: bool = False,
    plan: dict[str, Any] | None = None,
) -> str:
    root = config.WORKSPACE_ROOT
    remix = remix_url_for_session(session_id)
    vision = ""
    if has_attachments:
        vision = (
            "\nVisual reference:\n"
            "- The user attached screenshot(s). Treat them as the primary design spec.\n"
            "- Recreate layout, colors, typography, spacing, and component hierarchy "
            "as closely as practical with static HTML/CSS (no external CDNs).\n"
            f"- The same images are also on disk under {root}/app/reference/ if you "
            "need filenames; do not serve those reference files publicly unless asked.\n"
        )
    plan_block = plan_as_instructions(plan) if plan else ""
    return (
        "You are a senior front-end engineer with a Linux sandbox. Your job is to "
        "build a small web app the user describes and serve it on port 8080.\n\n"
        "Hard requirements:\n"
        f"- Workspace root is {root}. Put all sources under {root}/app/.\n"
        "- Use ONLY the Python standard library (http.server, html, json, sqlite3, "
        "etc.) unless the task truly needs more. The sandbox has no internet egress "
        "for arbitrary domains; only PyPI/apt mirrors are reachable.\n"
        "- Make the UI visually polished: real CSS, modern fonts (system stack is fine), "
        "responsive layout, no Bootstrap/CDNs (no internet). Inline assets.\n"
        "- Every public HTML page MUST include a fixed footer (or bottom bar) with "
        f'text exactly: \'Built with InstaVM Preview — <a href="{remix}">Remix</a>\' '
        "styled subtle and readable. Do not omit this.\n"
        "- Start the server in the background so this shell session can return:\n"
        f"    nohup python3 -m http.server 8080 --directory {root}/app/public >/tmp/srv.log 2>&1 &\n"
        "  (use a custom Python script for dynamic apps; bind to 0.0.0.0:8080.)\n"
        "- After starting, verify with `sleep 1 && curl -fsS http://127.0.0.1:8080/` "
        "and ensure HTTP 200.\n"
        "- If it works, your final message must be a short summary in JSON:\n"
        '    {"status":"ready","entrypoint":"<file>","stack":"<short>"}\n'
        "  No prose, no fences, no code blocks in the final message.\n"
        "- If you cannot make it serve, return:\n"
        '    {"status":"error","reason":"<short cause>"}\n'
        f"{plan_block}"
        f"{data_guidance()}"
        f"{tool_calling_rules()}"
        f"{vision}"
    )


def tool_calling_rules() -> str:
    return (
        "\nTool calling rules:\n"
        "- Prefer apply_patch (or write) to edit files. Do not use sed/awk for HTML edits.\n"
        "- exec_command `cmd` MUST be a single string, never a JSON array/list. "
        "Example: {\"cmd\": \"ls -la /home/appuser/workspace/app\"}.\n"
        "- After edits, restart the server if needed and verify with curl.\n"
        "- curl success alone is not enough: the body must be your app HTML, NOT a "
        "'Directory listing' page. Ensure index.html (or your server) is under "
        f"{config.WORKSPACE_ROOT}/app/public/ and being served.\n"
    )


async def _sandbox_sh(sandbox: Any, script: str, timeout: float = 60) -> str:
    result = await sandbox.exec("sh", "-c", script, timeout=timeout)
    out = getattr(result, "stdout", b"") or b""
    if isinstance(out, bytes):
        return out.decode("utf-8", "replace")
    return str(out)


async def ensure_http_server(sandbox: Any) -> str:
    """Make sure public/ is being served on :8080; return homepage diagnostics."""
    root = config.WORKSPACE_ROOT
    public = f"{root}/app/public"
    script = f"""
set +e
echo "=== public dir ==="
ls -la {public} 2>/dev/null || echo "missing public"
if [ ! -s {public}/index.html ]; then
  echo "MISSING_INDEX"
  exit 0
fi
echo "=== index head ==="
head -n 40 {public}/index.html

body=$(curl -fsS http://127.0.0.1:8080/ 2>/dev/null || true)
if echo "$body" | grep -Eiq '<html|<!doctype|<h1' && ! echo "$body" | grep -qi 'directory listing'; then
  echo "=== curl body ==="
  echo "$body"
  exit 0
fi

echo "=== restarting server ==="
pkill -f 'python3 -m http.server 8080' >/dev/null 2>&1 || true
sleep 0.4
nohup python3 -m http.server 8080 --bind 0.0.0.0 --directory {public} >/tmp/srv.log 2>&1 &
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 0.6
  body=$(curl -fsS http://127.0.0.1:8080/ 2>/dev/null || true)
  if echo "$body" | grep -qi 'directory listing'; then
    continue
  fi
  if echo "$body" | grep -Eiq '<html|<!doctype|<h1'; then
    echo "=== curl body ==="
    echo "$body"
    exit 0
  fi
done
echo "=== curl fallback ==="
curl -fsS http://127.0.0.1:8080/ 2>/dev/null || true
echo
echo "=== srv.log ==="
tail -n 30 /tmp/srv.log 2>/dev/null || true
"""
    return await _sandbox_sh(sandbox, script, timeout=120)


def preview_body_ok(body: str) -> bool:
    text = (body or "").strip()
    if "MISSING_INDEX" in text:
        return False
    if "=== curl body ===" in text:
        return preview_html_fragment_ok(text.split("=== curl body ===", 1)[-1])
    if "=== index head ===" in text:
        return preview_html_fragment_ok(text.split("=== index head ===", 1)[-1])
    return preview_html_fragment_ok(text)


def preview_html_fragment_ok(fragment: str) -> bool:
    text = (fragment or "").strip()
    if len(text) < 40:
        return False
    low = text.lower()
    if "directory listing" in low:
        return False
    return "<html" in low or "<!doctype" in low or "<h1" in low


def iterate_instructions(has_attachments: bool = False) -> str:
    root = config.WORKSPACE_ROOT
    vision = ""
    if has_attachments:
        vision = (
            " If screenshots are attached, treat them as visual targets and restyle "
            "toward that look while preserving existing functionality where possible."
        )
    return (
        "You are editing an existing web app already serving on port 8080 under "
        f"{root}/app/. Apply the user's change carefully and finish quickly.\n"
        "Workflow (keep it short):\n"
        f"1) Read the current files under {root}/app/ (usually public/index.html).\n"
        "2) Edit with apply_patch only — do not use sed.\n"
        "3) Restart the static server EXACTLY like this (do not change the directory):\n"
        f"   pkill -f 'python3 -m http.server 8080' || true; "
        f"nohup python3 -m http.server 8080 --bind 0.0.0.0 "
        f"--directory {root}/app/public >/tmp/srv.log 2>&1 &\n"
        "   (If the app uses a custom Python server script, restart that script on "
        "0.0.0.0:8080 instead — still one restart only.)\n"
        "4) Verify once: sleep 1 && curl -fsS http://127.0.0.1:8080/ | head\n"
        "5) Stop. Final message JSON only.\n"
        "Keep the 'Built with InstaVM Preview' footer if present."
        f"{vision} "
        f"{data_guidance()}"
        f"{tool_calling_rules()}"
        'Final message JSON only: {"status":"ready"} or {"status":"error","reason":"..."}.'
    )


def _user_message(prompt: str, attachments: list[Attachment], *, kind: str) -> Any:
    if kind == "build":
        text = (
            "Build the following app and start serving it on port 8080:\n\n"
            f"{prompt}"
        )
        if attachments:
            paths = ", ".join(reference_paths(attachments))
            text += (
                "\n\nAttached screenshot(s) are the visual reference. "
                f"Copies also live at: {paths}."
            )
    else:
        text = f"Apply this change to the running app:\n\n{prompt}"
        if attachments:
            text += "\n\nUse the attached screenshot(s) as the visual target."
    return agent_input(text, attachments)


def _format_build_error(exc: BaseException) -> str:
    """Surface useful sandbox stderr instead of opaque SDK messages."""
    ctx = getattr(exc, "context", None)
    if isinstance(ctx, dict):
        stderr = str(ctx.get("stderr") or "").strip()
        code = ctx.get("exit_code")
        if stderr:
            return f"{exc}: {stderr}"[:600]
        if code is not None:
            return f"{exc} (exit_code={code})"[:600]
    return str(exc)[:600]


def sse(event: str, data: dict[str, Any] | str) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def phase(phase_id: str, label: str, status: str, **extra: Any) -> bytes:
    payload: dict[str, Any] = {"id": phase_id, "label": label, "status": status}
    if extra:
        payload.update(extra)
    return sse("phase", payload)


async def with_heartbeats(
    inner: AsyncIterator[bytes], interval: float = config.HEARTBEAT_INTERVAL_S
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
    done = asyncio.Event()

    async def producer() -> None:
        try:
            async for chunk in inner:
                await queue.put(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("stream producer failed")
            try:
                await queue.put(sse("error", {"message": f"stream failed: {exc!s}"[:600]}))
                await queue.put(sse("done", {}))
            except Exception:
                pass
        finally:
            done.set()
            await queue.put(None)

    task = asyncio.create_task(producer())
    yield b": " + (b" " * 2048) + b"\n\n"
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                if done.is_set():
                    break
                yield b": keepalive\n\n"
                continue
            if chunk is None:
                break
            yield chunk
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


async def _delayed_delete(session_id: str, ttl: int) -> None:
    try:
        await asyncio.sleep(ttl)
    except asyncio.CancelledError:
        return
    session = await store.pop(session_id)
    if session is None:
        return
    try:
        await session.client.delete(session.sandbox)
    except Exception:
        logger.exception("failed to delete preview sandbox after TTL")


def _preview_url(endpoint: Any) -> str:
    scheme = "https" if endpoint.tls else "http"
    if scheme not in ("http", "https"):
        raise RuntimeError(f"unexpected sandbox endpoint scheme: {scheme!r}")
    if not _HOSTNAME_RE.match(endpoint.host or ""):
        raise RuntimeError(f"unexpected sandbox endpoint host: {endpoint.host!r}")
    port_part = ""
    if (endpoint.tls and endpoint.port not in (443, None)) or (
        not endpoint.tls and endpoint.port not in (80, None)
    ):
        port_part = f":{endpoint.port}"
    return f"{scheme}://{endpoint.host}{port_part}"


def _todo_done_events(text: str) -> list[bytes]:
    return [
        sse("todo", {"id": m.group(1), "status": "done"})
        for m in _TODO_DONE_RE.finditer(text or "")
    ]


async def _stream_agent_tools(
    stream: Any,
    *,
    todo_ids: list[str] | None = None,
) -> AsyncIterator[bytes]:
    pending = list(todo_ids or [])
    activated = False

    async for event in stream.stream_events():
        if event.type != "run_item_stream_event":
            continue
        if event.name == "tool_called":
            raw = getattr(event.item, "raw_item", None)
            name = getattr(raw, "name", "") or "tool"
            args = ""
            raw_args = getattr(raw, "arguments", None) or getattr(raw, "args", None)
            if isinstance(raw_args, str):
                args = raw_args
            elif raw_args is not None:
                try:
                    args = json.dumps(raw_args, default=str)[:1200]
                except Exception:
                    args = str(raw_args)[:1200]
            yield sse("tool_called", {"name": str(name), "args": args[:1200]})
            for chunk in _todo_done_events(args):
                yield chunk
            if pending and not activated:
                yield sse("todo", {"id": pending[0], "status": "active"})
                activated = True
        elif event.name == "tool_output":
            output = getattr(event.item, "output", "")
            if not isinstance(output, str):
                try:
                    output = json.dumps(output, default=str)
                except Exception:
                    output = str(output)
            yield sse("tool_output", {"output": output[:1500]})
            for chunk in _todo_done_events(output):
                yield chunk
                for m in _TODO_DONE_RE.finditer(output):
                    tid = m.group(1)
                    if tid in pending:
                        pending = [x for x in pending if x != tid]
                        if pending:
                            yield sse("todo", {"id": pending[0], "status": "active"})


def usage_from_stream(stream: Any) -> dict[str, Any]:
    """Read aggregated LLM usage from OpenAI Agents SDK run result."""
    empty: dict[str, Any] = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "model": config.MODEL_NAME,
    }
    try:
        wrapper = getattr(stream, "context_wrapper", None)
        usage = getattr(wrapper, "usage", None) if wrapper is not None else None
        if usage is None:
            return empty
        return {
            "requests": int(getattr(usage, "requests", 0) or 0),
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            "model": config.MODEL_NAME,
        }
    except Exception:
        logger.exception("failed to read LLM usage from stream")
        return empty


async def build_stream(
    prompt: str,
    guest_id: str,
    template_id: str | None = None,
    attachments: list[Attachment] | None = None,
    plan: dict[str, Any] | None = None,
) -> AsyncIterator[bytes]:
    attachments = attachments or []
    plan = normalize_plan(plan)
    session_id = store.new_session_id()
    yield sse(
        "phases",
        {
            "phases": [
                {"id": "provision", "label": "Provision sandbox"},
                {"id": "boot", "label": "Boot microVM"},
                {"id": "build", "label": "Build app"},
                {"id": "preview", "label": "Start preview"},
            ]
        },
    )
    todo_ids = [t["id"] for t in (plan or {}).get("todos") or []]
    if plan:
        yield sse(
            "todos",
            {
                "summary": plan["summary"],
                "todos": [
                    {"id": t["id"], "title": t["title"], "status": "pending"}
                    for t in plan["todos"]
                ],
            },
        )
    yield sse("session", {"session_id": session_id, "guest_id": guest_id})
    yield phase("provision", "Provision sandbox", "active")

    entries: dict[str, Any] = {
        "app/.keep": File(content=b""),
        "app/public/.keep": File(content=b""),
        "app/data/.keep": File(content=b""),
    }
    # Do not put binary images in Manifest — SDK entry serialization assumes
    # UTF-8 text. Write screenshots after boot via session.write().
    manifest = Manifest(root=config.WORKSPACE_ROOT, entries=entries)

    _, instavm_key = validate_keys()
    client = InstaVMSandboxClient(api_key=instavm_key)
    sandbox = None

    try:
        await store.begin_build()
        try:
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
            yield phase("provision", "Provision sandbox", "done")
            yield phase("boot", "Boot microVM", "active")
            await sandbox.start()
            if attachments:
                for i, att in enumerate(attachments):
                    path = Path(
                        f"{config.WORKSPACE_ROOT}/app/reference/"
                        f"{i + 1:02d}-{att.safe_filename}"
                    )
                    await sandbox.write(path, io.BytesIO(att.data))
            yield phase("boot", "Boot microVM", "done")
            yield phase("build", "Build app", "active")
            if todo_ids:
                yield sse("todo", {"id": todo_ids[0], "status": "active"})

            agent = SandboxAgent(
                name="Preview Builder",
                model=config.MODEL_NAME,
                instructions=builder_instructions(
                    session_id,
                    has_attachments=bool(attachments),
                    plan=plan,
                ),
                default_manifest=manifest,
            )
            stream = Runner.run_streamed(
                agent,
                _user_message(prompt, attachments, kind="build"),
                run_config=RunConfig(
                    sandbox=SandboxRunConfig(session=sandbox),
                    workflow_name="instavm-preview",
                ),
                max_turns=24,
            )
            async for chunk in _stream_agent_tools(stream, todo_ids=todo_ids):
                yield chunk

            for tid in todo_ids:
                yield sse("todo", {"id": tid, "status": "done"})

            usage = usage_from_stream(stream)
            yield sse("usage", usage)
            await store.record_guest_tokens(
                guest_id,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                total_tokens=usage["total_tokens"],
            )

            yield phase("build", "Build app", "done")
            yield phase("preview", "Start preview", "active")

            body = ""
            try:
                body = await ensure_http_server(sandbox)
            except Exception:
                logger.exception("preview readiness check failed")
            if not preview_body_ok(body):
                # One recovery turn: force a correct public/index.html serve path.
                yield sse(
                    "tool_output",
                    {
                        "output": "preview not ready (empty or directory listing) — recovery pass"
                    },
                )
                recover = Runner.run_streamed(
                    SandboxAgent(
                        name="Preview Builder Recovery",
                        model=config.MODEL_NAME,
                        instructions=builder_instructions(
                            session_id, has_attachments=bool(attachments)
                        ),
                    ),
                    (
                        "The preview URL is serving a Directory listing or empty page. "
                        f"Write a complete polished index.html under {config.WORKSPACE_ROOT}/app/public/ "
                        "for this request, start http.server on that directory on port 8080, "
                        "and verify curl returns real app HTML (not Directory listing).\n\n"
                        f"Original request:\n{prompt}"
                    ),
                    run_config=RunConfig(
                        sandbox=SandboxRunConfig(session=sandbox),
                        workflow_name="instavm-preview-recover",
                    ),
                    max_turns=12,
                )
                async for chunk in _stream_agent_tools(recover):
                    yield chunk
                extra = usage_from_stream(recover)
                for k in ("requests", "input_tokens", "output_tokens", "total_tokens"):
                    usage[k] = int(usage.get(k) or 0) + int(extra.get(k) or 0)
                yield sse("usage", usage)
                try:
                    body = await ensure_http_server(sandbox)
                except Exception:
                    logger.exception("preview readiness re-check failed")
            if not preview_body_ok(body):
                raise RuntimeError(
                    "Preview did not serve app HTML (got empty or directory listing). "
                    "Try again with a clearer UI prompt."
                )

            endpoint = await sandbox.resolve_exposed_port(config.PREVIEW_PORT)
            url = _preview_url(endpoint)
            now = time.time()
            session = PreviewSession(
                id=session_id,
                guest_id=guest_id,
                client=client,
                sandbox=sandbox,
                created_at=now,
                expires_at=now + config.PREVIEW_TTL_SECONDS,
                preview_url=url,
                prompt=prompt,
                template_id=template_id,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                total_tokens=usage["total_tokens"],
                llm_requests=usage["requests"],
            )
            await store.put(session)
            task = asyncio.create_task(
                _delayed_delete(session_id, config.PREVIEW_TTL_SECONDS)
            )
            session.cleanup_task = task
            store.track_task(task)
            sandbox = None

            quota = await store.record_guest_build(guest_id)
            yield phase("preview", "Start preview", "done")
            yield sse(
                "preview",
                {
                    "url": url,
                    "ttl_seconds": config.PREVIEW_TTL_SECONDS,
                    "session_id": session_id,
                    "remix_path": f"/?remix={session_id}",
                    "builds_remaining": max(
                        0, config.GUEST_BUILDS_PER_DAY - quota.builds
                    ),
                    "usage": usage,
                },
            )
        finally:
            await store.end_build()
    except Exception as exc:
        logger.exception("build failed")
        yield sse("error", {"message": _format_build_error(exc)})
        if sandbox is not None:
            try:
                await client.delete(sandbox)
            except Exception:
                logger.exception("failed to clean up sandbox after error")
    finally:
        yield sse("done", {})


async def iterate_stream(
    session_id: str,
    instruction: str,
    guest_id: str,
    attachments: list[Attachment] | None = None,
) -> AsyncIterator[bytes]:
    attachments = attachments or []
    session = await store.get(session_id)
    if session is None:
        yield sse("error", {"message": "Preview session expired or not found."})
        yield sse("done", {})
        return
    if session.guest_id != guest_id:
        yield sse("error", {"message": "Session does not belong to this guest."})
        yield sse("done", {})
        return
    if session.iterates_used >= config.GUEST_ITERATES_PER_SESSION:
        yield sse(
            "error",
            {
                "message": (
                    f"Iterate limit reached ({config.GUEST_ITERATES_PER_SESSION} "
                    "per preview). Save an account to keep going."
                )
            },
        )
        yield sse("done", {})
        return

    yield sse(
        "phases",
        {
            "phases": [
                {"id": "edit", "label": "Apply changes"},
                {"id": "preview", "label": "Refresh preview"},
            ]
        },
    )
    yield phase("edit", "Apply changes", "active")

    try:
        await store.begin_build()
        try:
            if attachments:
                for i, att in enumerate(attachments):
                    path = Path(
                        f"{config.WORKSPACE_ROOT}/app/reference/"
                        f"iterate-{session.iterates_used + 1:02d}-"
                        f"{i + 1:02d}-{att.safe_filename}"
                    )
                    await session.sandbox.write(path, io.BytesIO(att.data))

            user_input = _user_message(instruction, attachments, kind="iterate")
            last_exc: BaseException | None = None
            stream = None
            soft_complete = False
            for attempt in range(2):
                agent = SandboxAgent(
                    name="Preview Editor",
                    model=config.MODEL_NAME,
                    instructions=iterate_instructions(
                        has_attachments=bool(attachments)
                    ),
                )
                if attempt == 1:
                    user_input = agent_input(
                        "Your previous attempt failed because of an invalid tool call "
                        "(exec_command cmd must be a string, not a list). "
                        "Use apply_patch to edit files. Restart with the exact "
                        f"http.server --directory {config.WORKSPACE_ROOT}/app/public "
                        "command from your instructions. Then apply this change:\n\n"
                        f"{instruction}",
                        attachments,
                    )
                    yield sse(
                        "tool_output",
                        {
                            "output": "retrying after tool error — use apply_patch / string cmds"
                        },
                    )
                try:
                    stream = Runner.run_streamed(
                        agent,
                        user_input,
                        run_config=RunConfig(
                            sandbox=SandboxRunConfig(session=session.sandbox),
                            workflow_name="instavm-preview-iterate",
                        ),
                        max_turns=24,
                    )
                    async for chunk in _stream_agent_tools(stream):
                        yield chunk
                    last_exc = None
                    break
                except MaxTurnsExceeded as exc:
                    # Edits often landed; still refresh the live preview URL.
                    logger.warning("iterate hit max turns; returning preview anyway")
                    stream = getattr(exc, "result", None) or stream
                    soft_complete = True
                    last_exc = None
                    yield sse(
                        "tool_output",
                        {
                            "output": "max turns reached — refreshing preview with current files"
                        },
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc)
                    logger.warning("iterate attempt %s failed: %s", attempt + 1, msg)
                    if attempt == 0 and (
                        "validation error" in msg.lower()
                        or "exec_command" in msg.lower()
                        or "string_type" in msg.lower()
                    ):
                        continue
                    raise

            if last_exc is not None:
                raise last_exc

            usage = usage_from_stream(stream) if stream is not None else {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "model": config.MODEL_NAME,
            }
            if soft_complete:
                usage = {**usage, "soft_complete": True}
            yield sse("usage", usage)
            session.input_tokens += int(usage.get("input_tokens") or 0)
            session.output_tokens += int(usage.get("output_tokens") or 0)
            session.total_tokens += int(usage.get("total_tokens") or 0)
            session.llm_requests += int(usage.get("requests") or 0)
            await store.record_guest_tokens(
                guest_id,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )

            # Ensure public server is up after edits (idempotent).
            try:
                body = await ensure_http_server(session.sandbox)
                if not preview_body_ok(body):
                    yield sse(
                        "tool_output",
                        {"output": "warning: homepage still looks empty after restart"},
                    )
            except Exception:
                logger.debug("post-iterate server nudge skipped", exc_info=True)

            session.iterates_used += 1
            yield phase("edit", "Apply changes", "done")
            yield phase("preview", "Refresh preview", "done")
            yield sse(
                "preview",
                {
                    "url": session.preview_url,
                    "ttl_seconds": max(0, int(session.expires_at - time.time())),
                    "session_id": session.id,
                    "iterates_used": session.iterates_used,
                    "iterates_remaining": max(
                        0, config.GUEST_ITERATES_PER_SESSION - session.iterates_used
                    ),
                    "remix_path": f"/?remix={session.id}",
                    "usage": usage,
                    "session_usage": {
                        "input_tokens": session.input_tokens,
                        "output_tokens": session.output_tokens,
                        "total_tokens": session.total_tokens,
                        "requests": session.llm_requests,
                        "model": config.MODEL_NAME,
                    },
                },
            )
        finally:
            await store.end_build()
    except Exception as exc:
        logger.exception("iterate failed")
        yield sse("error", {"message": str(exc)[:600]})
    finally:
        yield sse("done", {})
