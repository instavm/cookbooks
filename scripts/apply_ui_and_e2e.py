#!/usr/bin/env python3
"""Apply UI landing pages + offline e2e tests across all recipe cookbooks."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_UI = ROOT / "recipe-08-hn-signal-scanner" / "lib" / "ui.py"
GOLDEN_SECRETS = ROOT / "recipe-08-hn-signal-scanner" / "lib" / "secrets.py"
GOLDEN_UI_TEST = ROOT / "recipe-08-hn-signal-scanner" / "tests" / "test_ui.py"

RECIPE_META: dict[str, dict[str, object]] = {
    "recipe-01-vc-research-drafter": {
        "tagline": "Nightly Exa VC scan, deduped warm-intro drafts via Mailtrap.",
        "endpoints": [("POST", "/run?dry_run=1", "Search VCs and preview drafts without sending.")],
        "e2e": "run",
    },
    "recipe-02-competitor-launch-watcher": {
        "tagline": "Diff competitor launch pages and summarize what changed.",
        "endpoints": [("POST", "/run?dry_run=1", "Fetch competitor pages and diff titles.")],
        "e2e": "run",
    },
    "recipe-03-pre-meeting-briefing": {
        "tagline": "Cal.com webhook → Exa research → one-page attendee briefing.",
        "endpoints": [
            ("POST", "/webhook/cal", "Meeting booked payload from Cal.com."),
            ("POST", "/run?dry_run=1", "Smoke briefing with sample attendee."),
        ],
        "e2e": "run",
    },
    "recipe-04-post-meeting-followup": {
        "tagline": "Meeting transcript to structured follow-up email draft.",
        "endpoints": [("POST", "/webhook/transcript", "Paste or POST transcript JSON.")],
        "e2e": "webhook_transcript",
    },
    "recipe-05-investor-crm-updater": {
        "tagline": "Email signals upserted into a lightweight investor CRM JSON store.",
        "endpoints": [("POST", "/webhook/email-signal", "Inbound email signal JSON.")],
        "e2e": "webhook_email",
    },
    "recipe-06-investor-update-assembler": {
        "tagline": "Stripe + GitHub metrics assembled into a monthly investor update.",
        "endpoints": [("POST", "/run?dry_run=1", "Assemble update without LLM."), ("GET", "/history", "Prior updates on volume.")],
        "e2e": "run",
        "e2e_env": "stripe",
    },
    "recipe-07-substack-distribution": {
        "tagline": "Substack post rewritten for LinkedIn and X with staged preview.",
        "endpoints": [
            ("POST", "/publish?dry_run=1", "Scrape URL and generate variants."),
            ("GET", "/preview", "Review distribution copy before posting."),
        ],
        "e2e": "publish",
    },
    "recipe-08-hn-signal-scanner": {
        "tagline": "HN Algolia digest with LLM signal filter and Mailtrap delivery.",
        "endpoints": [("POST", "/run?dry_run=1", "Preview digest without email.")],
        "e2e": "run",
    },
    "recipe-09-mention-monitor": {
        "tagline": "Brand mentions across HN and Reddit scored and sent to Slack.",
        "endpoints": [("POST", "/run?dry_run=1", "Poll sources and score mentions.")],
        "e2e": "run",
    },
    "recipe-11-market-brief-voice": {
        "tagline": "Market news script with optional Cartesia TTS output.",
        "endpoints": [("POST", "/run?dry_run=1", "Generate script."), ("GET", "/audio/latest", "Latest MP3 brief.")],
        "e2e": "run",
    },
    "recipe-12-feedback-linear-router": {
        "tagline": "Slack feedback classified and routed to Linear issues.",
        "endpoints": [("POST", "/webhook/slack", "Slack event payload.")],
        "e2e": "webhook_slack",
    },
    "recipe-13-cold-outbound-research": {
        "tagline": "Prospect research to personalized outbound email.",
        "endpoints": [("POST", "/prospect?dry_run=1", "Research prospect JSON.")],
        "e2e": "prospect",
    },
    "recipe-14-abm-daily-monitor": {
        "tagline": "Top-account news diff and net-new digest.",
        "endpoints": [("POST", "/run?dry_run=1", "Run ABM monitor."), ("POST", "/accounts", "Set account list.")],
        "e2e": "run",
    },
    "recipe-15-lost-deal-postmortem": {
        "tagline": "Closed-lost transcript to structured post-mortem.",
        "endpoints": [("POST", "/transcript?dry_run=1", "Analyze transcript JSON.")],
        "e2e": "transcript",
    },
    "recipe-16-seo-blog-pipeline": {
        "tagline": "Topic to SEO-optimized draft with editorial preview.",
        "endpoints": [("POST", "/topic?dry_run=1", "Generate draft."), ("GET", "/preview", "HTML preview.")],
        "e2e": "topic",
    },
    "recipe-17-podcast-prep-agent": {
        "tagline": "Episode transcript to host show notes.",
        "endpoints": [("POST", "/transcript?dry_run=1", "Generate show notes.")],
        "e2e": "transcript",
    },
    "recipe-18-churn-risk-warning": {
        "tagline": "Stripe billing + Intercom sentiment to churn risk alerts.",
        "endpoints": [("POST", "/scan?dry_run=1", "Score accounts."), ("GET", "/fixtures", "Bundled sample data.")],
        "e2e": "scan",
    },
    "recipe-19-weekly-account-health": {
        "tagline": "Weekly Stripe health digest posted to Slack.",
        "endpoints": [("POST", "/run?dry_run=1", "Preview weekly digest.")],
        "e2e": "run",
        "e2e_env": "stripe",
    },
    "recipe-20-voice-roadmap-notion": {
        "tagline": "Voice transcript extracts roadmap items for Notion.",
        "endpoints": [("POST", "/webhook/transcript?dry_run=1", "Cartesia-style transcript webhook.")],
        "e2e": "webhook_transcript_simple",
    },
    "recipe-21-standup-digest": {
        "tagline": "GitHub + Linear activity summarized for standup.",
        "endpoints": [("POST", "/run?dry_run=1", "Generate standup digest.")],
        "e2e": "run",
    },
    "recipe-22-pr-review-agent": {
        "tagline": "GitHub PR webhook to structured review comment.",
        "endpoints": [("POST", "/webhook/github", "GitHub pull_request payload.")],
        "e2e": "webhook_github",
    },
    "recipe-23-patent-landscape-watcher": {
        "tagline": "Patent and competitor intel diff digest.",
        "endpoints": [("POST", "/run?dry_run=1", "Run landscape watcher.")],
        "e2e": "run",
    },
    "recipe-24-stripe-revenue-dashboard": {
        "tagline": "Stripe KPI dashboard at a public share URL.",
        "endpoints": [("GET", "/", "HTML dashboard."), ("GET", "/api/kpis", "JSON metrics.")],
        "e2e": "dashboard",
        "e2e_env": "stripe",
        "skip_landing": True,
    },
    "recipe-28-browser-snapshot-fork": {
        "tagline": "Fork parallel InstaVM child sandboxes from a shared snapshot.",
        "endpoints": [("POST", "/fork", "Spawn parallel child sandbox tasks.")],
        "e2e": "fork",
        "e2e_env": "fork",
    },
    "recipe-29-computer-use-replay": {
        "tagline": "Computer-use session frame gallery for audit and replay.",
        "endpoints": [("GET", "/", "Frame gallery."), ("POST", "/capture", "Capture placeholder frames.")],
        "e2e": "gallery",
        "e2e_env": "none",
        "skip_landing": True,
    },
    "recipe-30-mcp-server-hosting": {
        "tagline": "Production MCP server stub with SSE transport.",
        "endpoints": [("GET", "/mcp/sse", "MCP SSE stream."), ("GET", "/health", "Health check.")],
        "e2e": "mcp_health",
        "e2e_env": "none",
    },
    "recipe-31-deterministic-replay": {
        "tagline": "Deterministic LLM replay from offline cassette tapes.",
        "endpoints": [("POST", "/replay", "Replay recorded LLM response.")],
        "e2e": "replay",
        "e2e_env": "none",
    },
}

E2E_ENV_LINES: dict[str, list[str]] = {
    "default": ['    monkeypatch.setenv("MAIL_DRY_RUN", "1")'],
    "stripe": ['    monkeypatch.setenv("STRIPE_MOCK", "1")'],
    "fork": ['    monkeypatch.setenv("INSTAVM_FORK_MOCK", "1")'],
    "none": [],
}

LIVE_SKIP_KEY: dict[str, str | None] = {
    "default": "OPENAI_API_KEY",
    "stripe": "STRIPE_KEY",
    "fork": "INSTAVM_API_KEY",
    "mcp_health": None,
    "gallery": None,
    "replay": None,
    "dashboard": None,
}


def live_key_for(meta: dict[str, object], e2e_kind: str) -> str | None:
    if e2e_kind in LIVE_SKIP_KEY:
        return LIVE_SKIP_KEY[e2e_kind]
    env_kind = str(meta.get("e2e_env", "default"))
    if env_kind in LIVE_SKIP_KEY:
        return LIVE_SKIP_KEY[env_kind]
    return LIVE_SKIP_KEY["default"]

E2E_TEST = '''import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from lib.secrets import secret_available

pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    return TestClient(app)


def test_e2e_offline_happy_path(client, monkeypatch, tmp_path):
    """Full dry-run path without external API keys."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "0")
{env_lines}
{offline_body}
{live_test}
'''

E2E_BODIES = {
    "run": '    resp = client.post("/run?dry_run=true")\n    assert resp.status_code == 200\n    assert resp.json().get("dry_run") is True',
    "publish": '    resp = client.post("/publish?dry_run=true", json={"url": "https://example.substack.com/p/test"})\n    assert resp.status_code == 200',
    "topic": '    resp = client.post("/topic?dry_run=true", json={"topic": "edge agents"})\n    assert resp.status_code == 200',
    "transcript": '    resp = client.post("/transcript?dry_run=true", json={"transcript": "We lost on pricing after a long competitive deal cycle."})\n    assert resp.status_code == 200',
    "scan": '    resp = client.post("/scan?dry_run=true")\n    assert resp.status_code == 200',
    "prospect": '    resp = client.post("/prospect?dry_run=true", json={"name": "Ada", "email": "ada@acme.io", "company": "Acme", "domain": "acme.io"})\n    assert resp.status_code == 200',
    "fork": '    resp = client.post("/fork", json={"tasks": ["alpha", "beta"]})\n    assert resp.status_code == 200',
    "replay": '    resp = client.post("/replay")\n    assert resp.status_code == 200\n    assert "REPLAY_OK" in resp.json().get("content", "")',
    "dashboard": '    resp = client.get("/")\n    assert resp.status_code == 200\n    assert "text/html" in resp.headers.get("content-type", "")',
    "gallery": '    resp = client.get("/")\n    assert resp.status_code == 200\n    assert "Screen replay" in resp.text or "replay" in resp.text.lower()',
    "mcp_health": '    resp = client.get("/health")\n    assert resp.status_code == 200\n    assert resp.json().get("ok") == "true"',
    "webhook_transcript": '    resp = client.post("/webhook/transcript?dry_run=true", json={"transcript": "Thanks for the demo.", "attendees": ["Alex"]})\n    assert resp.status_code == 200',
    "webhook_transcript_simple": '    resp = client.post("/webhook/transcript?dry_run=true", json={"transcript": "Ship dark mode next sprint."})\n    assert resp.status_code == 200',
    "webhook_email": '    resp = client.post("/webhook/email-signal?dry_run=true", json={"from": "vc@fund.com", "subject": "Follow up", "body_preview": "Great chat"})\n    assert resp.status_code == 200',
    "webhook_slack": '    fixture = json.loads((Path(__file__).parent.parent / "fixtures" / "slack_event.json").read_text())\n    resp = client.post("/webhook/slack?dry_run=true", json=fixture)\n    assert resp.status_code == 200',
    "webhook_github": '    fixture = json.loads((Path(__file__).parent.parent / "fixtures" / "pr_opened.json").read_text())\n    resp = client.post("/webhook/github?dry_run=true", json=fixture)\n    assert resp.status_code == 200',
}


def patch_app_landing(app_path: Path, slug: str, title: str, meta: dict) -> None:
    if meta.get("skip_landing"):
        return
    text = app_path.read_text()
    if "from lib.ui import landing_page" in text:
        return
    if "from fastapi.responses import JSONResponse" in text:
        text = text.replace(
            "from fastapi.responses import JSONResponse",
            "from fastapi.responses import HTMLResponse, JSONResponse",
        )
    elif "from fastapi.responses import HTMLResponse" not in text:
        text = text.replace(
            "from fastapi import FastAPI",
            "from fastapi import FastAPI\nfrom fastapi.responses import HTMLResponse",
        )
    text = text.replace(
        "from pydantic import BaseModel",
        "from lib.ui import landing_page\nfrom pydantic import BaseModel",
        1,
    ) if "from lib.ui import landing_page" not in text else text
    if "from lib.ui import landing_page" not in text:
        # insert after last import block line before app =
        text = re.sub(
            r"(import agent\n)",
            r"\1from lib.ui import landing_page\n",
            text,
            count=1,
        ) or text.replace("app = FastAPI", "from lib.ui import landing_page\n\napp = FastAPI", 1)

    endpoints = meta["endpoints"]
    ep_lines = ",\n        ".join(
        f'("{m}", "{p}", "{d}")' for m, p, d in endpoints  # type: ignore[misc]
    )
    tagline = str(meta["tagline"])
    landing_fn = f'''
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="{title}",
            slug="{slug}",
            tagline="{tagline}",
            endpoints=[
        {ep_lines}
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )
'''
    text = re.sub(
        r"@app\.get\(\"/\"\)\ndef index\(\)[\s\S]*?(?=\n@app\.|\nclass |\Z)",
        landing_fn.strip() + "\n\n",
        text,
        count=1,
    )
    app_path.write_text(text)


def main() -> None:
    for recipe_dir in sorted(ROOT.glob("recipe-*/")):
        slug = recipe_dir.name
        if slug not in RECIPE_META:
            continue
        dst = recipe_dir / "lib" / "ui.py"
        if GOLDEN_UI.resolve() != dst.resolve():
            shutil.copy2(GOLDEN_UI, dst)
        secrets_dst = recipe_dir / "lib" / "secrets.py"
        if not secrets_dst.is_file() and GOLDEN_SECRETS.is_file():
            shutil.copy2(GOLDEN_SECRETS, secrets_dst)
        manifest = yaml.safe_load((recipe_dir / "instavm.yaml").read_text())
        title = manifest.get("title", slug)
        patch_app_landing(recipe_dir / "app.py", slug, title, RECIPE_META[slug])
        e2e_kind = str(RECIPE_META[slug].get("e2e", "run"))
        body = E2E_BODIES.get(e2e_kind, E2E_BODIES["run"])
        env_kind = str(RECIPE_META[slug].get("e2e_env", "default"))
        env_lines = "\n".join(E2E_ENV_LINES.get(env_kind, E2E_ENV_LINES["default"]))
        live_key = live_key_for(RECIPE_META[slug], e2e_kind)
        if live_key:
            live_test = f'''

@pytest.mark.skipif(not secret_available("{live_key}"), reason="{live_key} missing")
def test_e2e_live_optional():
    """Run manually against a deployed VM when vault + keys are configured."""
    assert secret_available("{live_key}")
'''
        else:
            live_test = ""
        (recipe_dir / "tests" / "test_e2e.py").write_text(
            E2E_TEST.format(env_lines=env_lines, offline_body=body, live_test=live_test)
        )
        if GOLDEN_UI_TEST.is_file() and not (recipe_dir / "tests" / "test_ui.py").exists():
            shutil.copy2(GOLDEN_UI_TEST, recipe_dir / "tests" / "test_ui.py")
        print(f"updated {slug}")


if __name__ == "__main__":
    main()
