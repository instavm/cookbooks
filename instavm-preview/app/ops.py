"""Direct InstaVM client actions — sandbox/VM ops with a live PTY, not a web-app build."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from . import config
from . import ops_registry
from .build import sse, validate_keys
from .intent import classify_intent

logger = logging.getLogger("instavm_preview.ops")

_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
    re.I,
)

_OPS = frozenset(
    {
        "create_session",
        "set_egress",
        "credits",
        "execute",
        "open_pty",
        "list_vms",
        "suspend",
        "resume",
        "cleanup",
    }
)


def looks_like_ops(prompt: str, *, has_ops_context: bool = False) -> bool:
    return classify_intent(prompt, has_ops_context=has_ops_context) == "ops"


def _wants_cleanup(prompt: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(kill|destroy|delete|terminate|stop|cleanup|clean\s*up)\b.{"
            r"0,40}\b(vm|sandbox|session)\b|"
            r"\b(kill|destroy|delete|terminate)\s+(it|this|that)\b",
            prompt,
        )
    )


def _heuristic_actions(
    prompt: str, *, context: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    text = prompt.strip()
    lower = text.lower()
    ctx = context or {}
    ctx_vm = (ctx.get("vm_id") or "").strip() or None
    ctx_sid = (ctx.get("session_id") or "").strip() or None
    actions: list[dict[str, Any]] = []

    if re.search(r"(?i)\b(list|show|what)\b.+\b(vms?|sandboxes|sessions)\b", lower) or re.search(
        r"(?i)\b(my\s+)?(current\s+)?vms?\b", lower
    ):
        if not re.search(r"(?i)\b(create|start|spin|launch)\b", lower):
            return [{"op": "list_vms", "label": "List VMs"}]

    if re.search(r"(?i)\bsuspend\b", lower):
        item: dict[str, Any] = {"op": "suspend", "label": "Suspend VM"}
        if ctx_vm:
            item["vm_id"] = ctx_vm
        return [item]

    if re.search(r"(?i)\bresume\b", lower):
        item = {"op": "resume", "label": "Resume VM"}
        if ctx_vm:
            item["vm_id"] = ctx_vm
        return [item]

    if _wants_cleanup(text) and (ctx_sid or ctx_vm):
        item = {"op": "cleanup", "label": "Stop sandbox"}
        if ctx_sid:
            item["session_id"] = ctx_sid
        return [item]

    wants_session = bool(
        re.search(r"(?i)\b(create|start|spin\s*up|launch)\b.+\b(sandbox|session|vm)\b", lower)
        or re.search(r"(?i)\bsandbox\s+with\b", lower)
        or "start_session" in lower
    )
    wants_egress = bool(re.search(r"(?i)\begress|allow\s*-?\s*list|allowlist", lower))

    if wants_session or wants_egress:
        actions.append({"op": "create_session", "label": "Create sandbox"})

    if wants_egress:
        domains = [d.lower() for d in _DOMAIN_RE.findall(text)]
        domains = [
            d
            for d in domains
            if d not in {"instavm.io", "api.instavm.io", "openai.com"}
            and not d.endswith(".png")
        ]
        star = bool(
            re.search(
                r"(?i)(\*\s*allowlist|allowlist\s*\*|allow\s+all|open\s+egress|unrestricted)",
                text,
            )
        )
        deny = bool(re.search(r"(?i)\b(deny|block|no\s+egress|lockdown)\b", lower))

        if deny and not star:
            actions.append(
                {
                    "op": "set_egress",
                    "label": "Deny egress",
                    "allow_http": False,
                    "allow_https": False,
                    "allow_package_managers": False,
                    "allowed_domains": [],
                    "allowed_cidrs": [],
                }
            )
        elif domains and not star:
            actions.append(
                {
                    "op": "set_egress",
                    "label": f"Allowlist ({', '.join(domains[:6])})",
                    "allow_http": False,
                    "allow_https": True,
                    "allow_package_managers": True,
                    "allowed_domains": domains[:20],
                    "allowed_cidrs": [],
                }
            )
        else:
            actions.append(
                {
                    "op": "set_egress",
                    "label": "Open egress (*)",
                    "allow_http": True,
                    "allow_https": True,
                    "allow_package_managers": True,
                    "allowed_domains": [],
                    "allowed_cidrs": [],
                }
            )

    if re.search(r"(?i)\bcredits?\b", lower) and not actions:
        actions.append({"op": "credits", "label": "Credits"})

    if not actions and ctx_sid:
        # Follow-up with no clear verb — keep session, refresh terminal
        actions.append({"op": "open_pty", "label": "Open terminal"})
    elif not actions:
        actions = [
            {"op": "create_session", "label": "Create sandbox"},
            {
                "op": "set_egress",
                "label": "Package-manager egress",
                "allow_http": False,
                "allow_https": False,
                "allow_package_managers": True,
                "allowed_domains": [],
                "allowed_cidrs": [],
            },
        ]

    if any(a["op"] == "create_session" for a in actions) and not _wants_cleanup(text):
        if not any(a["op"] == "open_pty" for a in actions):
            actions.append({"op": "open_pty", "label": "Open terminal"})

    return actions


def _normalize_actions(actions: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    """Hard rules: never auto-kill; always open a terminal after create."""
    out: list[dict[str, Any]] = []
    for a in actions:
        op = str(a.get("op") or "")
        if op == "cleanup" and not _wants_cleanup(prompt):
            continue
        out.append(a)
    if any(a.get("op") == "create_session" for a in out) and not _wants_cleanup(prompt):
        if not any(a.get("op") == "open_pty" for a in out):
            out.append({"op": "open_pty", "label": "Open terminal"})
    return out or [{"op": "open_pty", "label": "Open terminal"}]


def _prefer_heuristic(prompt: str) -> bool:
    """Skip LLM for clear sandbox/ops phrasing — LLM kept inventing cleanup."""
    return bool(
        re.search(
            r"(?is)\b(sandbox|allowlist|allow\s*-?\s*list|egress|suspend|resume|"
            r"list\s+(my\s+)?(current\s+)?vms?|create\s+(a\s+)?(session|vm)|"
            r"open\s+(a\s+)?(terminal|shell|pty)|kill\s+(this|the)\s+(vm|sandbox))\b",
            prompt,
        )
    )


async def extract_ops(
    prompt: str, *, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return {summary, actions} for direct InstaVM client execution."""
    ctx = context or {}
    heuristic = _normalize_actions(_heuristic_actions(prompt, context=ctx), prompt)
    summary = (
        "Sandbox ready"
        if any(a["op"] == "create_session" for a in heuristic)
        else "Running"
    )

    if _prefer_heuristic(prompt):
        return {"summary": summary, "actions": heuristic, "mode": "ops"}

    try:
        validate_keys()
        client = AsyncOpenAI()
        ctx_note = ""
        if ctx.get("session_id") or ctx.get("vm_id"):
            ctx_note = (
                f" Active context: session_id={ctx.get('session_id')!r} "
                f"vm_id={ctx.get('vm_id')!r}."
            )
        resp = await client.chat.completions.create(
            model=config.MODEL_NAME,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Map natural language to InstaVM Python client ops. "
                        "Return ONLY JSON: "
                        '{"summary":"short human status","actions":[{"op":"…","label":"…",…}]}. '
                        "Allowed op values: create_session, set_egress, credits, execute, "
                        "open_pty, list_vms, suspend, resume, cleanup. "
                        "NOT a web-app build — never invent HTML/CSS todos. "
                        "For '* allowlist' / allow all → open egress (http+https true, domains []). "
                        "After create_session, include open_pty so the user gets a terminal. "
                        "NEVER add cleanup/kill unless the user explicitly asked to stop/kill "
                        "the VM/session. Keep sandboxes alive for follow-ups."
                        + ctx_note
                    ),
                },
                {"role": "user", "content": prompt.strip()[:2000]},
            ],
        )
        raw = json.loads(resp.choices[0].message.content or "{}")
        actions = raw.get("actions") if isinstance(raw, dict) else None
        if isinstance(actions, list) and actions:
            cleaned: list[dict[str, Any]] = []
            for a in actions[:10]:
                if not isinstance(a, dict):
                    continue
                op = str(a.get("op") or "").strip()
                if op not in _OPS:
                    continue
                item = {"op": op, "label": str(a.get("label") or op)[:120]}
                for k in (
                    "allow_http",
                    "allow_https",
                    "allow_package_managers",
                    "allowed_domains",
                    "allowed_cidrs",
                    "code",
                    "vm_id",
                    "session_id",
                ):
                    if k in a:
                        item[k] = a[k]
                cleaned.append(item)
            cleaned = _normalize_actions(cleaned, prompt)
            if cleaned:
                return {
                    "summary": str(raw.get("summary") or summary)[:160],
                    "actions": cleaned,
                    "mode": "ops",
                }
    except Exception:
        logger.exception("ops LLM extract failed; using heuristic")

    return {"summary": summary, "actions": heuristic, "mode": "ops"}


def _client():
    from instavm import InstaVM

    key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    # `timeout` doubles as HTTP timeout and vm_lifetime_seconds on start_session.
    # Keep it long enough for interactive PTY; short lifetimes kill the shell mid-session.
    return InstaVM(
        api_key=key,
        timeout=1800,
        memory_mb=1024,
        cpu_count=1,
        auto_start_session=False,
    )


def _resolve_vm_id(client: Any, session_id: str | None) -> str | None:
    if not session_id:
        return None
    # Prefer /status — session info often has no vm_id until later.
    try:
        status = client.get_session_status(session_id)
        if isinstance(status, dict):
            for key in ("vm_id", "microvm_id", "sandbox_id"):
                val = status.get(key)
                if val:
                    return str(val)
    except Exception:
        logger.debug("get_session_status failed for %s", session_id, exc_info=True)
    try:
        info = client.get_session_info(session_id)
        if isinstance(info, dict):
            for key in ("vm_id", "microvm_id", "sandbox_id"):
                val = info.get(key)
                if val:
                    return str(val)
    except Exception:
        logger.exception("get_session_info failed for %s", session_id)
    return None


def _pty_transient_auth_error(exc: BaseException) -> bool:
    """Guest agent 401s (missing agent token) are mapped by the SDK to auth errors."""
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "invalid api key",
            "session expired",
            "invalid or missing token",
            "authentication",
            "401",
        )
    )


async def _create_pty(
    client: Any, *, session_id: str | None, vm_id: str | None
) -> tuple[str, str, str | None]:
    """Create a PTY; retry guest-agent auth races; prefer VM route then session route.

    Returns (pty_id, upstream_ws_url, vm_id_used).
    """
    vid = vm_id
    sid = session_id
    last_exc: BaseException | None = None

    for attempt in range(10):
        if sid and not vid:
            vid = await _wait_for_vm_id(client, sid, attempts=3, delay_s=0.4)
        elif sid and attempt > 0:
            refreshed = await asyncio.to_thread(_resolve_vm_id, client, sid)
            if refreshed:
                vid = refreshed

        try:
            if vid:
                pty = await asyncio.to_thread(client.pty.create_for_vm, vid, 100, 32)
                pty_id = str(
                    (pty or {}).get("session_id") or (pty or {}).get("id") or ""
                )
                if not pty_id:
                    raise RuntimeError("PTY create returned no id.")
                upstream = client.pty.ws_url_for_vm(vid, pty_id)
                return pty_id, upstream, vid
            if sid:
                pty = await asyncio.to_thread(client.pty.create, sid, 100, 32)
                pty_id = str(
                    (pty or {}).get("session_id") or (pty or {}).get("id") or ""
                )
                if not pty_id:
                    raise RuntimeError("PTY create returned no id.")
                upstream = client.pty.ws_url(sid, pty_id)
                return pty_id, upstream, vid
            raise RuntimeError("No sandbox/VM for terminal.")
        except Exception as exc:
            last_exc = exc
            if attempt < 9 and _pty_transient_auth_error(exc):
                logger.warning(
                    "PTY create attempt %s failed (%s); retrying for guest agent readiness",
                    attempt + 1,
                    exc,
                )
                await asyncio.sleep(min(0.5 * (attempt + 1), 3.0))
                continue
            # Fall back once from VM-scoped to session-scoped before giving up.
            if vid and sid and attempt < 9:
                try:
                    pty = await asyncio.to_thread(client.pty.create, sid, 100, 32)
                    pty_id = str(
                        (pty or {}).get("session_id") or (pty or {}).get("id") or ""
                    )
                    if pty_id:
                        upstream = client.pty.ws_url(sid, pty_id)
                        return pty_id, upstream, vid
                except Exception as fallback_exc:
                    last_exc = fallback_exc
                    if _pty_transient_auth_error(fallback_exc):
                        await asyncio.sleep(min(0.5 * (attempt + 1), 3.0))
                        continue
            break

    assert last_exc is not None
    raise last_exc


async def _wait_for_vm_id(
    client: Any, session_id: str | None, *, attempts: int = 30, delay_s: float = 1.0
) -> str | None:
    """Session create can return before a microVM is bound — poll like dash does."""
    if not session_id:
        return None
    for _ in range(attempts):
        vid = await asyncio.to_thread(_resolve_vm_id, client, session_id)
        if vid:
            return vid
        await asyncio.sleep(delay_s)
    return None


def _format_vm_list(rows: list[Any]) -> str:
    if not rows:
        return "No VMs found."
    lines = []
    for row in rows[:40]:
        if not isinstance(row, dict):
            lines.append(str(row)[:200])
            continue
        vid = row.get("vm_id") or row.get("id") or "?"
        status = row.get("status") or row.get("state") or ""
        name = row.get("name") or row.get("label") or ""
        bit = f"{vid}"
        if status:
            bit += f"  {status}"
        if name:
            bit += f"  {name}"
        lines.append(bit)
    return "\n".join(lines)


async def ops_stream(
    prompt: str,
    guest_id: str,
    *,
    session_id: str | None = None,
    vm_id: str | None = None,
) -> AsyncIterator[bytes]:
    """Execute InstaVM client ops and stream progress (SSE)."""
    context = {
        "session_id": (session_id or "").strip() or None,
        "vm_id": (vm_id or "").strip() or None,
    }
    packed = await extract_ops(prompt, context=context)
    actions = _normalize_actions(list(packed["actions"]), prompt)
    yield sse(
        "ops",
        {
            "summary": packed["summary"],
            "actions": [
                {"id": f"a{i}", "label": a.get("label") or a["op"], "status": "pending"}
                for i, a in enumerate(actions)
            ],
        },
    )

    client = None
    sid: str | None = context["session_id"]
    vid: str | None = context["vm_id"]
    pty_id: str | None = None
    pty_path: str | None = None

    try:
        validate_keys()
        client = await asyncio.to_thread(_client)
        if sid and not vid:
            vid = await _wait_for_vm_id(client, sid, attempts=5, delay_s=0.5)

        for i, action in enumerate(actions):
            aid = f"a{i}"
            label = action.get("label") or action["op"]
            yield sse("todo", {"id": aid, "status": "active"})
            yield sse("status", {"message": label})
            op = action["op"]
            try:
                if op == "create_session":
                    sid = await asyncio.to_thread(client.start_session)
                    yield sse("status", {"message": "Waiting for VM…"})
                    vid = await _wait_for_vm_id(client, sid)
                    if not vid:
                        raise RuntimeError("Sandbox created but no VM was assigned.")
                    yield sse(
                        "session",
                        {"session_id": sid, "guest_id": guest_id, "vm_id": vid},
                    )
                    yield sse(
                        "status",
                        {"message": f"Sandbox created · {vid}"},
                    )

                elif op == "set_egress":
                    if not sid:
                        sid = client.session_id or await asyncio.to_thread(
                            client.start_session
                        )
                        vid = await asyncio.to_thread(_resolve_vm_id, client, sid)
                    kwargs = {
                        "allow_package_managers": bool(
                            action.get("allow_package_managers", True)
                        ),
                        "allow_http": bool(action.get("allow_http", False)),
                        "allow_https": bool(action.get("allow_https", True)),
                        "allowed_domains": list(action.get("allowed_domains") or []),
                        "allowed_cidrs": list(action.get("allowed_cidrs") or []),
                    }
                    await asyncio.to_thread(
                        client.set_session_egress, sid, **kwargs
                    )
                    yield sse("status", {"message": "Egress updated"})

                elif op == "credits":
                    summary = await asyncio.to_thread(client.credits.summary)
                    yield sse(
                        "ops_result",
                        {
                            "title": "Credits",
                            "text": json.dumps(summary, default=str, indent=2)[:4000],
                        },
                    )

                elif op == "execute":
                    code = str(action.get("code") or "print('ok')")[:4000]
                    if not sid:
                        sid = client.session_id or await asyncio.to_thread(
                            client.start_session
                        )
                    out = await asyncio.to_thread(client.execute, code)
                    text = out if isinstance(out, str) else json.dumps(out, default=str)
                    yield sse(
                        "ops_result",
                        {"title": "Output", "text": str(text)[:4000]},
                    )

                elif op == "list_vms":
                    rows = await asyncio.to_thread(client.vms.list)
                    yield sse(
                        "ops_result",
                        {"title": "VMs", "text": _format_vm_list(rows)},
                    )

                elif op == "suspend":
                    target = (
                        str(action.get("vm_id") or "").strip()
                        or vid
                        or await asyncio.to_thread(_resolve_vm_id, client, sid)
                    )
                    if not target:
                        raise RuntimeError("No VM to suspend — create a sandbox first.")
                    await asyncio.to_thread(client.vms.suspend, target)
                    vid = target
                    yield sse("status", {"message": f"Suspended {target}"})

                elif op == "resume":
                    target = (
                        str(action.get("vm_id") or "").strip()
                        or vid
                        or await asyncio.to_thread(_resolve_vm_id, client, sid)
                    )
                    if not target:
                        raise RuntimeError("No VM to resume — create a sandbox first.")
                    out = await asyncio.to_thread(client.vms.resume, target)
                    if isinstance(out, dict):
                        new_id = out.get("vm_id") or out.get("id")
                        if new_id:
                            vid = str(new_id)
                        else:
                            vid = target
                    else:
                        vid = target
                    yield sse("status", {"message": f"Resumed · {vid}"})
                    # Fresh shell after resume
                    if not any(a.get("op") == "open_pty" for a in actions[i + 1 :]):
                        actions.append({"op": "open_pty", "label": "Open terminal"})

                elif op == "open_pty":
                    if not vid and sid:
                        vid = await _wait_for_vm_id(client, sid)
                    if not vid and not sid:
                        raise RuntimeError("No sandbox/VM for terminal.")
                    pty_id, upstream, vid = await _create_pty(
                        client, session_id=sid, vm_id=vid
                    )
                    token = ops_registry.register(
                        guest_id=guest_id,
                        session_id=sid,
                        vm_id=vid,
                        pty_id=pty_id,
                        upstream_ws=upstream,
                    )
                    pty_path = f"/ws/pty/{token}"
                    yield sse("status", {"message": "Terminal ready"})

                elif op == "cleanup":
                    target_sid = (
                        str(action.get("session_id") or "").strip()
                        or sid
                        or client.session_id
                    )
                    if not target_sid:
                        raise RuntimeError("Nothing to stop.")
                    await asyncio.to_thread(client.kill, target_sid)
                    sid = None
                    vid = None
                    pty_id = None
                    pty_path = None
                    yield sse("status", {"message": "Sandbox stopped"})

                else:
                    raise RuntimeError(f"Unsupported op: {op}")

                yield sse("todo", {"id": aid, "status": "done"})
            except Exception as exc:
                logger.exception("ops action failed: %s", op)
                yield sse("todo", {"id": aid, "status": "error"})
                yield sse(
                    "error",
                    {"message": f"{label} failed: {exc!s}"[:500]},
                )
                yield sse("done", {"mode": "ops", "ok": False})
                return

        done_payload: dict[str, Any] = {
            "summary": packed["summary"],
            "session_id": sid,
            "vm_id": vid,
            "pty_id": pty_id,
            "pty_path": pty_path,
            "message": packed["summary"] if not pty_path else "Terminal ready",
        }
        yield sse("ops_done", done_payload)
        yield sse(
            "session",
            {"session_id": sid, "guest_id": guest_id, "vm_id": vid},
        )
    except Exception as exc:
        logger.exception("ops stream failed")
        yield sse("error", {"message": f"Ops failed: {exc!s}"[:500]})
    finally:
        yield sse("done", {"mode": "ops", "ok": True})
