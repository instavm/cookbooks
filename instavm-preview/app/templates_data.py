"""Starter templates for InstaVM Preview."""

from __future__ import annotations

from typing import TypedDict


class Template(TypedDict):
    id: str
    title: str
    blurb: str
    prompt: str


class OpsExample(TypedDict):
    id: str
    prompt: str


TEMPLATES: list[Template] = [
    {
        "id": "landing",
        "title": "Shop landing",
        "blurb": "One-page storefront with menu and hours.",
        "prompt": (
            "Build a single-page landing site for a neighborhood coffee shop "
            "called Harbor Roast. Include a strong hero with the shop name, a "
            "short menu (3 drinks, 2 pastries), hours, and a simple contact "
            "form that stores submissions in memory for this session. Polished "
            "typography and layout. No external CDNs."
        ),
    },
    {
        "id": "crm",
        "title": "Tiny CRM",
        "blurb": "Add contacts, search, mark follow-ups.",
        "prompt": (
            "Build a tiny personal CRM backed by sqlite3. Put the database file "
            "under app/data/ (not public/). Users can add a contact (name, email, "
            "note), search by name, toggle a follow-up flag, and delete. Clean "
            "table UI, no frameworks, no CDNs. Serve on port 8080."
        ),
    },
    {
        "id": "dashboard",
        "title": "Ops dashboard",
        "blurb": "Fake metrics with filters and a chart.",
        "prompt": (
            "Build an operations dashboard with three KPI cards (requests, "
            "error rate, p95 latency), a simple SVG line chart of the last 12 "
            "hours of fake traffic, and a filter for environment "
            "(prod / staging). All data generated in Python. Polished dark "
            "UI, no CDNs, serve on 8080."
        ),
    },
    {
        "id": "game",
        "title": "Browser game",
        "blurb": "Playable snake with score and restart.",
        "prompt": (
            "Build a playable Snake game in vanilla HTML/CSS/JS. Arrow keys "
            "and WASD, score display, pause, restart. Smooth grid, readable "
            "instructions, no CDNs. Serve the static files on port 8080."
        ),
    },
    {
        "id": "form",
        "title": "Feedback form",
        "blurb": "Collect feedback with a thank-you state.",
        "prompt": (
            "Build a product feedback form: rating 1–5, short text, optional "
            "email. On submit, store in sqlite3 under app/data/ and show a calm "
            "thank-you state with the ability to submit another. Include a simple "
            "admin list at /admin showing recent entries. No CDNs. Port 8080."
        ),
    },
]


# Rotating prompt ideas for InstaVM client / sandbox ops (not web-app builds).
OPS_EXAMPLES: list[OpsExample] = [
    {
        "id": "claude-code",
        "prompt": "create a sandbox with claude code template",
    },
    {
        "id": "codex",
        "prompt": "Launch the codex template and open a terminal",
    },
    {
        "id": "egress-star",
        "prompt": (
            "Create a sandbox with * allowlist so the VM can reach the public internet, "
            "then open a terminal"
        ),
    },
    {
        "id": "egress-domains",
        "prompt": (
            "Spin up a session, allowlist egress for api.github.com and pypi.org, "
            "and drop me into a shell"
        ),
    },
    {
        "id": "pm-only",
        "prompt": (
            "Start a sandbox with package-manager egress only — no open HTTP/HTTPS — "
            "and give me a PTY"
        ),
    },
    {
        "id": "list-vms",
        "prompt": "List my current VMs with their status",
    },
    {
        "id": "suspend",
        "prompt": "Suspend this VM so it parks without burning host resources",
    },
    {
        "id": "resume",
        "prompt": "Resume the suspended VM and open a fresh terminal",
    },
    {
        "id": "credits",
        "prompt": "Show my InstaVM credits summary",
    },
    {
        "id": "kill",
        "prompt": "Kill this sandbox when you're done — stop the session cleanly",
    },
]


def list_templates() -> list[Template]:
    return TEMPLATES


def list_ops_examples() -> list[OpsExample]:
    return OPS_EXAMPLES


def get_template(template_id: str) -> Template | None:
    for item in TEMPLATES:
        if item["id"] == template_id:
            return item
    return None
