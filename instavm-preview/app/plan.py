"""Pre-build plan generation (no sandbox) — summary + checklist todos."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from . import config

logger = logging.getLogger("instavm_preview.plan")

_TODO_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,24}$")


def normalize_plan(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    summary = str(raw.get("summary") or "").strip()[:400]
    todos_in = raw.get("todos")
    if not summary or not isinstance(todos_in, list) or not todos_in:
        return None
    todos: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(todos_in[:8]):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or f"t{i + 1}").strip().lower()
        tid = re.sub(r"[^a-z0-9_]", "", tid)[:24] or f"t{i + 1}"
        if tid in seen:
            tid = f"{tid}{i + 1}"
        seen.add(tid)
        title = str(item.get("title") or "").strip()[:120]
        if not title:
            continue
        todos.append({"id": tid, "title": title})
    if len(todos) < 2:
        return None
    return {"summary": summary, "todos": todos}


def plan_as_instructions(plan: dict[str, Any]) -> str:
    lines = "\n".join(
        f"- [{t['id']}] {t['title']}" for t in plan.get("todos") or []
    )
    return (
        "\nApproved build plan (follow this; do not expand scope):\n"
        f"{plan.get('summary', '')}\n\n"
        "Checklist — complete in order. When you finish an item, echo exactly "
        "[[todo:done:ID]] in a shell command (e.g. `echo '[[todo:done:t1]]'`) "
        "before moving on:\n"
        f"{lines}\n"
    )


async def generate_plan(
    prompt: str,
    *,
    feedback: str | None = None,
    previous: dict[str, Any] | None = None,
    has_attachments: bool = False,
) -> dict[str, Any]:
    """Cheap structured plan — no microVM."""
    client = AsyncOpenAI()
    user_parts = [
        f"User request:\n{prompt.strip()}",
    ]
    if has_attachments:
        user_parts.append(
            "(Screenshots were attached — plan a faithful visual recreation "
            "with static HTML/CSS where possible.)"
        )
    if previous:
        user_parts.append(
            "Previous plan JSON:\n"
            + json.dumps(previous, ensure_ascii=False)[:2000]
        )
    if feedback and feedback.strip():
        user_parts.append(f"User wants these changes to the plan:\n{feedback.strip()}")

    system = (
        "You are the planning step for InstaVM Preview. Propose a short build "
        "plan for a small web app that will run in an isolated microVM with "
        "Python stdlib + HTML/CSS only (no CDNs, no Postgres).\n"
        "Return ONLY valid JSON with this shape:\n"
        '{"summary":"1-2 sentences","todos":[{"id":"t1","title":"…"},…]}\n'
        "Rules:\n"
        "- summary: what will be built (not how the infra works)\n"
        "- 3 to 6 todos, each one concrete and checkable\n"
        "- ids: short snake-ish like t1, layout, api, style, serve\n"
        "- last todo should be about verifying / serving the app\n"
        "- no markdown fences, no prose outside JSON"
    )

    resp = await client.chat.completions.create(
        model=config.MODEL_NAME,
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("plan JSON parse failed: %s", text[:300])
        raise RuntimeError("Model returned an invalid plan. Try again.") from None

    plan = normalize_plan(raw)
    if plan is None:
        raise RuntimeError("Plan was too vague — try a clearer prompt.")

    usage = getattr(resp, "usage", None)
    meta = {
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "model": config.MODEL_NAME,
    }
    return {"plan": plan, "usage": meta}
