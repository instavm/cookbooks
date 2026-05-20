#!/usr/bin/env python3
"""Apply manifest post_deploy_notes and expand stub READMEs from recipe metadata."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

RECIPE_DOCS: dict[str, dict[str, str]] = {
    "recipe-06-investor-update-assembler": {
        "title": "Investor Update Assembler",
        "num": "06",
        "summary": "Stripe + GitHub metrics assembled into a monthly investor update.",
        "vault_hosts": "api.stripe.com, api.github.com, api.openai.com",
        "verify": "GET /health, then POST /run?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-07-substack-distribution": {
        "title": "Substack Distribution",
        "num": "07",
        "summary": "Substack post rewritten for LinkedIn and X with staged preview.",
        "vault_hosts": "api.firecrawl.dev, api.openai.com",
        "verify": "GET /health, POST /publish?dry_run=1, GET /preview",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-09-mention-monitor": {
        "title": "Mention Monitor",
        "num": "09",
        "summary": "Brand mentions across HN and Reddit scored and sent to Slack.",
        "vault_hosts": "api.openai.com, hooks.slack.com",
        "verify": "GET /health, POST /run?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-11-market-brief-voice": {
        "title": "Market Brief Voice",
        "num": "11",
        "summary": "Market news script with optional Cartesia TTS output.",
        "vault_hosts": "api.linkup.so, api.cartesia.ai, api.openai.com",
        "verify": "GET /health, POST /run?dry_run=1, GET /audio/latest",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-12-feedback-linear-router": {
        "title": "Feedback Linear Router",
        "num": "12",
        "summary": "Slack feedback classified and routed to Linear issues.",
        "vault_hosts": "api.linear.app, api.openai.com",
        "verify": "GET /health, POST /webhook/slack?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-19-weekly-account-health": {
        "title": "Weekly Account Health",
        "num": "19",
        "summary": "Weekly Stripe health digest posted to Slack.",
        "vault_hosts": "api.stripe.com, slack.com, api.openai.com",
        "verify": "GET /health, POST /run?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-20-voice-roadmap-notion": {
        "title": "Voice Roadmap Notion",
        "num": "20",
        "summary": "Voice transcript extracts roadmap items for Notion.",
        "vault_hosts": "api.notion.com, api.openai.com",
        "verify": "GET /health, POST /webhook/transcript?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-21-standup-digest": {
        "title": "Standup Digest",
        "num": "21",
        "summary": "GitHub + Linear activity summarized for standup.",
        "vault_hosts": "api.github.com, api.linear.app, slack.com",
        "verify": "GET /health, POST /run?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-22-pr-review-agent": {
        "title": "PR Review Agent",
        "num": "22",
        "summary": "GitHub PR webhook to structured review comment.",
        "vault_hosts": "api.github.com, api.openai.com",
        "verify": "GET /health, POST /webhook/github?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-23-patent-landscape-watcher": {
        "title": "Patent Landscape Watcher",
        "num": "23",
        "summary": "Patent and competitor intel diff digest.",
        "vault_hosts": "api.exa.ai, api.firecrawl.dev, api.openai.com",
        "verify": "GET /health, POST /run?dry_run=1",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
    "recipe-24-stripe-revenue-dashboard": {
        "title": "Stripe Revenue Dashboard",
        "num": "24",
        "summary": "Live Stripe KPI dashboard at a public share URL.",
        "vault_hosts": "api.stripe.com",
        "verify": "GET /health, GET / for HTML dashboard, GET /api/kpis for JSON",
        "local": "pytest tests/test_unit.py tests/test_smoke.py",
    },
}

README_TEMPLATE = """# {title} (Recipe #{num})

{summary}

## Why InstaVM

| Feature | Why it matters |
|---------|----------------|
| Persistent volume | Recipe state survives restarts when configured |
| Egress allowlist | Only required upstream hosts are reachable |
| Vault-injected keys | API keys never stored in VM environment |

## Prerequisites

- InstaVM CLI ≥ 0.23
- Org vault bound to: {vault_hosts}
- For local tests set `ALLOW_LOCAL_SECRETS=1` or use `*_MOCK=1` flags

## Deploy

```bash
cd {slug}
instavm vault setup .
instavm deploy --plan .
instavm deploy .
```

## Verify

1. Open the share URL → {verify}
2. Use `?dry_run=1` on POST routes when testing without live sends

## Local tests

```bash
export ALLOW_LOCAL_SECRETS=1
pip install -r requirements.txt
{local}
```
"""

POST_DEPLOY: dict[str, list[str]] = {
    "recipe-24-stripe-revenue-dashboard": [
        "Run `instavm vault setup .` to bind api.stripe.com (STRIPE_KEY).",
        "Open share URL → GET /health, then GET / for the HTML dashboard.",
        "Set STRIPE_MOCK=1 via --env for offline demo data.",
    ],
    "recipe-29-computer-use-replay": [
        "No vault required — placeholder frames are generated locally.",
        "Open share URL → GET / for frame gallery, POST /capture to refresh.",
    ],
    "recipe-30-mcp-server-hosting": [
        "No third-party vault hosts — MCP SSE stub only.",
        "GET /health and GET /mcp/sse on the share URL.",
    ],
    "recipe-31-deterministic-replay": [
        "Bind api.openai.com via vault for live replay; cassette works offline.",
        "POST /replay returns REPLAY_OK from fixtures/cassette.jsonl.",
    ],
    "recipe-28-browser-snapshot-fork": [
        "Bind instavm.dev / platform API via INSTAVM_KEY for live forks.",
        "Set INSTAVM_FORK_MOCK=1 for offline parallel child stubs.",
    ],
}


def patch_manifest(slug: str) -> None:
    path = ROOT / slug / "instavm.yaml"
    if not path.is_file():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if slug in POST_DEPLOY:
        data["post_deploy_notes"] = POST_DEPLOY[slug]
    elif slug in RECIPE_DOCS:
        hosts = RECIPE_DOCS[slug]["vault_hosts"]
        verify = RECIPE_DOCS[slug]["verify"]
        data["post_deploy_notes"] = [
            f"Run `instavm vault setup .` — bind {hosts}.",
            verify,
        ]
    # Remove generic OPENAI_KEY/EXA_KEY boilerplate if still present as first note only
    path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"manifest {slug}")


def patch_readme(slug: str) -> None:
    if slug not in RECIPE_DOCS:
        return
    meta = RECIPE_DOCS[slug]
    meta["slug"] = slug
    text = README_TEMPLATE.format(**meta)
    (ROOT / slug / "README.md").write_text(text, encoding="utf-8")
    print(f"readme {slug}")


def main() -> None:
    for slug in sorted(RECIPE_DOCS):
        patch_readme(slug)
        patch_manifest(slug)
    for slug in POST_DEPLOY:
        if slug not in RECIPE_DOCS:
            patch_manifest(slug)


if __name__ == "__main__":
    main()
