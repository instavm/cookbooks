"""Match natural-language prompts to InstaVM platform (devbox) templates."""

from __future__ import annotations

import re
import shlex
from typing import Any

# Prefer longer phrases first. Aliases map to catalog slugs from GET /v1/templates.
_TEMPLATE_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("claude-code", ("claude code", "claude-code", "anthropic claude")),
    ("code-server", ("code server", "code-server", "vscode server")),
    ("open-webui", ("open webui", "open-webui", "openwebui")),
    ("cursor-cli", ("cursor cli", "cursor-cli")),
    ("gemini-cli", ("gemini cli", "gemini-cli")),
    ("opencode", ("open code", "opencode", "open-code")),
    ("jupyter", ("jupyter", "jupyterlab", "jupyter notebook")),
    ("codex", ("openai codex", "codex")),
    ("copilot", ("github copilot", "copilot")),
    ("devbox", ("plain devbox", "empty devbox", "base devbox")),
    ("aider", ("aider",)),
    ("cline", ("cline",)),
    ("crush", ("crush",)),
    ("devin", ("devin",)),
    ("goose", ("goose",)),
    ("hermes", ("hermes",)),
    ("pi", ("pi agent",)),
]

_KNOWN_SLUGS = frozenset(slug for slug, _ in _TEMPLATE_ALIASES)
_PTY_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ash", "fish", "ksh", "csh", "tcsh"})
_TERM_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def _alias_in_text(text: str, alias: str) -> bool:
    alias_l = alias.strip().lower()
    if not alias_l:
        return False
    if " " in alias_l or "-" in alias_l:
        # Normalize hyphens/spaces so "claude-code" matches "claude code".
        pattern = re.escape(alias_l).replace(r"\-", r"[\s-]+").replace(r"\ ", r"[\s-]+")
        return bool(re.search(rf"(?i)(?<![a-z0-9]){pattern}(?![a-z0-9])", text))
    return bool(re.search(rf"(?i)\b{re.escape(alias_l)}\b", text))


def match_template_slug(prompt: str) -> str | None:
    """Return a platform template slug if the prompt asks to launch one."""
    text = (prompt or "").strip().lower()
    if not text:
        return None

    # 1) Multi-word / hyphenated aliases first (avoid "code template" stealing
    #    the trailing token from "claude code template").
    for slug, aliases in _TEMPLATE_ALIASES:
        multi = [a for a in aliases if (" " in a or "-" in a)]
        for alias in sorted(multi, key=len, reverse=True):
            if _alias_in_text(text, alias):
                return slug

    # 2) Explicit "template <slug>" / "<slug> template"
    m = re.search(
        r"(?i)\b(?:template|devbox|coding[- ]?agent)\s+([a-z0-9][a-z0-9._-]{1,63})\b|"
        r"\b([a-z0-9][a-z0-9._-]{1,63})\s+template\b",
        text,
    )
    if m:
        candidate = (m.group(1) or m.group(2) or "").strip().lower().replace("_", "-")
        if candidate in _KNOWN_SLUGS:
            return candidate
        for slug, aliases in _TEMPLATE_ALIASES:
            if candidate == slug or candidate in {a.replace(" ", "-") for a in aliases}:
                return slug
        # Unknown but explicit slug — still try to run it.
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", candidate):
            return candidate

    # 3) Single-token aliases (codex, aider, …)
    for slug, aliases in _TEMPLATE_ALIASES:
        singles = [a for a in aliases if " " not in a and "-" not in a]
        for alias in singles:
            if _alias_in_text(text, alias):
                return slug
    return None


def wants_platform_template(prompt: str) -> bool:
    return match_template_slug(prompt) is not None


def compose_pty_command(terminal: dict[str, Any] | None, *, term: str = "xterm-256color") -> str | None:
    """Build the shell command used by `instavm open` for template terminals."""
    if not isinstance(terminal, dict) or not terminal:
        return None
    local_term = term if _TERM_SAFE.match(term) and term != "dumb" else "xterm-256color"
    command = str(terminal.get("command") or "").strip()
    if not command:
        return None
    prefix = f"export TERM={local_term}; "
    cwd = str(terminal.get("cwd") or "").strip()
    if cwd:
        prefix += f"cd {shlex.quote(cwd)} 2>/dev/null || true; "
    if command.rsplit("/", 1)[-1] in _PTY_SHELLS:
        return f"{prefix}exec {shlex.quote(command)}"
    session = str(terminal.get("tmux_session") or "").strip() or "main"
    return (
        f"{prefix}command -v tmux >/dev/null 2>&1 && "
        f"exec tmux new -A -s {shlex.quote(session)} {shlex.quote(command)} "
        f"|| exec {command}"
    )


def resolve_slug_against_catalog(slug: str, templates: list[dict[str, Any]]) -> str:
    """Map aliases from the live catalog onto canonical slugs when possible."""
    normalized = (slug or "").strip()
    if not normalized:
        return normalized
    for template in templates:
        if template.get("slug") == normalized:
            return normalized
    for template in templates:
        aliases = template.get("aliases") or []
        if normalized in aliases:
            return str(template.get("slug") or normalized)
        name = str(template.get("name") or "").strip().lower()
        if name and name == normalized.lower():
            return str(template.get("slug") or normalized)
    return normalized
