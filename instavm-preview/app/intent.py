"""Route prompts: InstaVM client ops vs web-app builds."""

from __future__ import annotations

import re
from typing import Literal

from .template_resolve import match_template_slug

Intent = Literal["ops", "webapp"]

_OPS_RE = re.compile(
    r"(?is)\b("
    r"instavm(\s+client|\s+sdk|\s+api)?|"
    r"start[_\s-]?session|kill[_\s-]?session|end[_\s-]?session|"
    r"set[_\s-]?session[_\s-]?egress|egress(\s+policy)?|"
    r"allow[\s-]?list|allowlist|"
    r"create\s+(a\s+)?(sandbox|session|vm|microvm|devbox)|"
    r"spin\s*up\s+(a\s+)?(sandbox|session|vm|devbox)|"
    r"sandbox\s+with|"
    r"(claude[- ]?code|codex|opencode|code[- ]?server|jupyter)\s*(template)?|"
    r"(template|devbox)\s+[a-z0-9][a-z0-9._-]{1,63}|"
    r"[a-z0-9][a-z0-9._-]{1,63}\s+template|"
    r"suspend|resume|"
    r"list\s+(my\s+)?(current\s+)?(vms?|sandboxes|sessions)|"
    r"(my\s+)?(current\s+)?vms?\b|"
    r"volume(s)?\s+(create|mount|list)|"
    r"credits?(\s+summary)?|"
    r"ssh\s+(into|to|access)|"
    r"kill\s+(the\s+)?(vm|sandbox|session)|"
    r"this\s+(vm|sandbox|session)"
    r")\b"
)

_WEBAPP_RE = re.compile(
    r"(?is)\b("
    r"landing\s*page|web\s*app|website|todo\s*app|html|css|"
    r"shop|crm|dashboard\s+ui|browser\s+game|feedback\s+form|"
    r"build\s+(me\s+)?(a\s+)?(page|site|app)|"
    r"screenshot|looks?\s+like"
    r")\b"
)

_META_APP_RE = re.compile(
    r"(?is)\b(sandbox\s+web\s+app|run\s+python\s+snippets|"
    r"isolated,?\s+allowlisted\s+environment|textarea\s+for\s+code)\b"
)


def classify_intent(prompt: str, *, has_ops_context: bool = False) -> Intent:
    """Fast heuristic — ops wins for InstaVM primitives / follow-ups."""
    text = (prompt or "").strip()
    if not text:
        return "webapp"

    ops = bool(_OPS_RE.search(text)) or bool(match_template_slug(text))
    web = bool(_WEBAPP_RE.search(text))

    # Follow-ups like "suspend this" / "resume it" while in an ops conversation
    if has_ops_context and re.search(
        r"(?is)\b(suspend|resume|kill|stop|list|egress|allowlist|this|that|it|them)\b",
        text,
    ):
        if not web or len(text) < 80:
            return "ops"

    if ops and not web:
        return "ops"
    if ops and web and _META_APP_RE.search(text):
        return "webapp"
    if ops and re.search(r"(?is)\b(create|start|spin|suspend|resume|list).{0,40}\b(sandbox|session|vm)", text):
        if re.search(r"(?is)\b(html|css|frontend|landing|page\s+with)\b", text):
            return "webapp"
        return "ops"
    if web and not ops:
        return "webapp"
    return "webapp"


def looks_like_ops(prompt: str, *, has_ops_context: bool = False) -> bool:
    return classify_intent(prompt, has_ops_context=has_ops_context) == "ops"
