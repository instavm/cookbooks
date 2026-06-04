#!/usr/bin/env python3
"""Scaffold standalone recipe cookbooks from recipe-08 golden template."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "recipe-08-hn-signal-scanner"

RECIPES = [
    ("01", "recipe-01-vc-research-drafter", "VC Research Drafter", "Exa VC search with warm-intro email drafts."),
    ("02", "recipe-02-competitor-launch-watcher", "Competitor Launch Watcher", "Diff competitor pages and summarize launches."),
    ("03", "recipe-03-pre-meeting-briefing", "Pre-Meeting Briefing", "Webhook-triggered attendee research briefings."),
    ("04", "recipe-04-post-meeting-followup", "Post-Meeting Follow-up", "Transcript to structured follow-up draft."),
    ("05", "recipe-05-investor-crm-updater", "Investor CRM Updater", "Email signals to CRM JSON upserts."),
    ("06", "recipe-06-investor-update-assembler", "Investor Update Assembler", "Stripe and GitHub metrics to investor update."),
    ("07", "recipe-07-substack-distribution", "Substack Distribution", "Rewrite posts for LinkedIn and X."),
    ("09", "recipe-09-mention-monitor", "Mention Monitor", "Brand mention polling with Slack alerts."),
    ("11", "recipe-11-market-brief-voice", "Market Brief Voice", "Market news script with optional TTS."),
    ("12", "recipe-12-feedback-linear-router", "Feedback Linear Router", "Slack feedback to Linear issues."),
    ("13", "recipe-13-cold-outbound-research", "Cold Outbound Research", "Prospect research to personalized email."),
    ("14", "recipe-14-abm-daily-monitor", "ABM Daily Monitor", "Account news diff and digest."),
    ("15", "recipe-15-lost-deal-postmortem", "Lost Deal Post-Mortem", "Transcript to structured post-mortem."),
    ("16", "recipe-16-seo-blog-pipeline", "SEO Blog Pipeline", "Topic to SEO-optimized draft preview."),
    ("17", "recipe-17-podcast-prep-agent", "Podcast Prep Agent", "Transcript to show notes."),
    ("18", "recipe-18-churn-risk-warning", "Churn Risk Warning", "Billing and sentiment to churn alerts."),
    ("19", "recipe-19-weekly-account-health", "Weekly Account Health", "Stripe weekly digest to Slack."),
    ("20", "recipe-20-voice-roadmap-notion", "Voice Roadmap Notion", "Voice transcript to roadmap items."),
    ("21", "recipe-21-standup-digest", "Standup Digest", "GitHub and Linear to standup summary."),
    ("22", "recipe-22-pr-review-agent", "PR Review Agent", "PR webhook to review comments."),
    ("23", "recipe-23-patent-landscape-watcher", "Patent Landscape Watcher", "Patent/competitor intel digest."),
    ("24", "recipe-24-stripe-revenue-dashboard", "Stripe Revenue Dashboard", "Live Stripe KPI dashboard."),
    ("28", "recipe-28-browser-snapshot-fork", "Browser Snapshot Fork", "Parallel InstaVM child sandbox demo."),
    ("29", "recipe-29-computer-use-replay", "Computer Use Replay", "Screenshot gallery replay demo."),
    ("30", "recipe-30-mcp-server-hosting", "MCP Server Hosting", "FastMCP server with vault placeholders."),
    ("31", "recipe-31-deterministic-replay", "Deterministic Replay", "LLM cassette replay demo."),
]


def scaffold(num: str, slug: str, title: str, summary: str) -> None:
    dest = ROOT / slug
    if dest.exists():
        return
    shutil.copytree(GOLDEN, dest, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache"))
    # Update instavm.yaml slug/title
    manifest = dest / "instavm.yaml"
    text = manifest.read_text()
    text = text.replace("recipe-08-hn-signal-scanner", slug)
    text = text.replace("HN Signal Scanner", title)
    text = text.replace("Cron-style HN digest with LLM filtering and Mailtrap delivery on InstaVM.", summary)
    manifest.write_text(text)
    # Update app health slug
    app = dest / "app.py"
    app.write_text(app.read_text().replace("recipe-08-hn-signal-scanner", slug).replace("HN Signal Scanner", title))
    readme = dest / "README.md"
    readme.write_text(
        f"# {title} (Recipe #{num})\n\n{summary}\n\n## Deploy\n\n```bash\ncd {slug}\ninstavm vault setup .\ninstavm deploy --plan .\ninstavm deploy .\n```\n\n## Verify\n\n1. `GET /health`\n2. `POST /run?dry_run=1`\n\nSee recipe-08-hn-signal-scanner for the golden template patterns.\n"
    )


def main() -> None:
    for num, slug, title, summary in RECIPES:
        scaffold(num, slug, title, summary)
        print(f"scaffolded {slug}")


if __name__ == "__main__":
    main()
