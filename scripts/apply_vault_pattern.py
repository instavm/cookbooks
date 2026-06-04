#!/usr/bin/env python3
"""Apply InstaVM vault credential injection pattern across all recipe cookbooks."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "recipe-08-hn-signal-scanner" / "lib"

LLM_HOSTS = ["api.openai.com", "api.anthropic.com"]

RECIPE_VAULT: dict[str, dict[str, list[str]]] = {
    "recipe-01-vc-research-drafter": {
        "hosts": LLM_HOSTS + ["api.exa.ai"],
        "egress": ["api.exa.ai", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-02-competitor-launch-watcher": {
        "hosts": LLM_HOSTS,
        "egress": [],  # scrape targets vary via COMPETITOR_URLS
    },
    "recipe-03-pre-meeting-briefing": {
        "hosts": LLM_HOSTS + ["api.exa.ai"],
        "egress": ["api.exa.ai"],
    },
    "recipe-04-post-meeting-followup": {"hosts": LLM_HOSTS, "egress": []},
    "recipe-05-investor-crm-updater": {"hosts": LLM_HOSTS, "egress": []},
    "recipe-06-investor-update-assembler": {
        "hosts": LLM_HOSTS + ["api.stripe.com", "api.github.com"],
        "egress": ["api.stripe.com", "api.github.com"],
    },
    "recipe-07-substack-distribution": {
        "hosts": LLM_HOSTS + ["api.firecrawl.dev"],
        "egress": ["api.firecrawl.dev"],
    },
    "recipe-08-hn-signal-scanner": {
        "hosts": LLM_HOSTS,
        "egress": ["hn.algolia.com", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-09-mention-monitor": {
        "hosts": LLM_HOSTS,
        "egress": ["hn.algolia.com", "www.reddit.com", "hooks.slack.com"],
    },
    "recipe-11-market-brief-voice": {
        "hosts": LLM_HOSTS + ["api.linkup.so", "api.cartesia.ai"],
        "egress": ["api.linkup.so", "api.cartesia.ai"],
    },
    "recipe-12-feedback-linear-router": {
        "hosts": LLM_HOSTS + ["api.linear.app"],
        "egress": ["api.linear.app"],
    },
    "recipe-13-cold-outbound-research": {
        "hosts": LLM_HOSTS + ["api.exa.ai"],
        "egress": ["api.exa.ai", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-14-abm-daily-monitor": {
        "hosts": LLM_HOSTS + ["api.linkup.so"],
        "egress": ["api.linkup.so", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-15-lost-deal-postmortem": {"hosts": LLM_HOSTS, "egress": []},
    "recipe-16-seo-blog-pipeline": {"hosts": LLM_HOSTS, "egress": []},
    "recipe-17-podcast-prep-agent": {
        "hosts": LLM_HOSTS + ["api.cartesia.ai"],
        "egress": ["api.cartesia.ai"],
    },
    "recipe-18-churn-risk-warning": {
        "hosts": LLM_HOSTS,
        "egress": ["hooks.slack.com", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-19-weekly-account-health": {
        "hosts": LLM_HOSTS + ["api.stripe.com"],
        "egress": ["api.stripe.com", "hooks.slack.com"],
    },
    "recipe-20-voice-roadmap-notion": {
        "hosts": LLM_HOSTS + ["api.notion.com"],
        "egress": ["api.notion.com"],
    },
    "recipe-21-standup-digest": {
        "hosts": LLM_HOSTS + ["api.github.com", "api.linear.app"],
        "egress": ["api.github.com", "api.linear.app", "hooks.slack.com"],
    },
    "recipe-22-pr-review-agent": {
        "hosts": LLM_HOSTS + ["api.github.com"],
        "egress": ["api.github.com"],
    },
    "recipe-23-patent-landscape-watcher": {
        "hosts": LLM_HOSTS + ["api.exa.ai", "api.firecrawl.dev"],
        "egress": ["api.exa.ai", "api.firecrawl.dev", "sandbox.smtp.mailtrap.io"],
    },
    "recipe-24-stripe-revenue-dashboard": {
        "hosts": ["api.stripe.com"],
        "egress": ["api.stripe.com"],
    },
    "recipe-28-browser-snapshot-fork": {
        "hosts": ["api.instavm.io"],
        "egress": ["api.instavm.io"],
        "required": True,
    },
    "recipe-29-computer-use-replay": {"hosts": [], "egress": []},
    "recipe-30-mcp-server-hosting": {
        "hosts": LLM_HOSTS,
        "egress": [],
        "required": False,
    },
    "recipe-31-deterministic-replay": {
        "hosts": ["api.openai.com"],
        "egress": ["api.openai.com"],
        "required": False,
    },
}

INTEGRATION_PATCHES: list[tuple[str, str, str]] = [
    # (glob-ish path suffix, old, new) — applied per file if old found
]

REPLACEMENTS_INTEGRATIONS = [
    ("from lib.secrets import load_secret", "from lib.secrets import mock_enabled, vault_credential"),
    ("load_secret(\"EXA_API_KEY\") or \"EXA_KEY\"", "vault_credential(\"EXA_API_KEY\")"),
    ("load_secret(\"EXA_API_KEY\") or os.environ.get(\"EXA_API_KEY\", \"EXA_KEY\")", "vault_credential(\"EXA_API_KEY\")"),
    ("load_secret(\"EXA_API_KEY\") or os.environ.get(\"EXA_API_KEY\", \"\")", "vault_credential(\"EXA_API_KEY\")"),
    ("key = load_secret(\"EXA_API_KEY\")", "key = vault_credential(\"EXA_API_KEY\")"),
    ('os.environ.get("EXA_MOCK", "1") == "1" or not load_secret("EXA_API_KEY")', "mock_enabled(\"EXA_MOCK\")"),
    ("load_secret(\"FIRECRAWL_API_KEY\")", "vault_credential(\"FIRECRAWL_API_KEY\")"),
    ('os.environ.get("FIRECRAWL_TEST_MODE", "1") == "1" or not load_secret("FIRECRAWL_API_KEY")', "mock_enabled(\"FIRECRAWL_MOCK\") or mock_enabled(\"FIRECRAWL_TEST_MODE\")"),
    ("load_secret(\"STRIPE_KEY\")", "vault_credential(\"STRIPE_KEY\")"),
    ("load_secret(\"STRIPE_RESTRICTED_KEY\")", "vault_credential(\"STRIPE_RESTRICTED_KEY\")"),
    ("load_secret(\"GITHUB_TOKEN\")", "vault_credential(\"GITHUB_TOKEN\")"),
    ("load_secret(\"LINEAR_API_KEY\")", "vault_credential(\"LINEAR_API_KEY\")"),
    ('os.environ.get("LINEAR_TEST_MODE", "1") == "1" or not load_secret("LINEAR_API_KEY")', "mock_enabled(\"LINEAR_MOCK\") or mock_enabled(\"LINEAR_TEST_MODE\")"),
    ("load_secret(\"LINKUP_API_KEY\")", "vault_credential(\"LINKUP_API_KEY\")"),
    ("load_secret(\"NOTION_TOKEN\")", "vault_credential(\"NOTION_TOKEN\")"),
    ("load_secret(\"CARTESIA_API_KEY\")", "vault_credential(\"CARTESIA_API_KEY\")"),
    ("load_secret(\"SLACK_WEBHOOK_URL\")", "vault_credential(\"SLACK_WEBHOOK_URL\")"),
    ("load_secret(\"SLACK_TOKEN\")", "vault_credential(\"SLACK_TOKEN\")"),
    ("load_secret(\"INSTAVM_API_KEY\")", "vault_credential(\"INSTAVM_API_KEY\")"),
    (" or not load_secret(\"EXA_API_KEY\")", ""),
    (" or not load_secret(\"FIRECRAWL_API_KEY\")", ""),
    (" or not load_secret(\"STRIPE_KEY\")", ""),
    (" or not load_secret(\"STRIPE_RESTRICTED_KEY\")", ""),
    (" or not load_secret(\"GITHUB_TOKEN\")", ""),
    (" or not load_secret(\"LINEAR_API_KEY\")", ""),
    (" or not load_secret(\"LINKUP_API_KEY\")", ""),
    (" or not load_secret(\"NOTION_TOKEN\")", ""),
    (" or not load_secret(\"CARTESIA_API_KEY\")", ""),
    (" or not load_secret(\"SLACK_WEBHOOK_URL\")", ""),
]

CONFIG_MOCK_DEFAULTS = [
    ('os.environ.get("STRIPE_MOCK", "1")', 'os.environ.get("STRIPE_MOCK", "")'),
    ('os.environ.get("NOTION_MOCK", "1")', 'os.environ.get("NOTION_MOCK", "")'),
    ('os.environ.get("EXA_MOCK", "1")', 'os.environ.get("EXA_MOCK", "")'),
    ('os.environ.get("FIRECRAWL_MOCK", "1")', 'os.environ.get("FIRECRAWL_MOCK", "")'),
    ('os.environ.get("GITHUB_MOCK", "1")', 'os.environ.get("GITHUB_MOCK", "")'),
    ('os.environ.get("LINEAR_MOCK", "1")', 'os.environ.get("LINEAR_MOCK", "")'),
    ('os.environ.get("COMPETITOR_MOCK", "1")', 'os.environ.get("COMPETITOR_MOCK", "")'),
    ('os.environ.get("FIRECRAWL_TEST_MODE", "1")', 'os.environ.get("FIRECRAWL_TEST_MODE", "")'),
]


def sync_lib(recipe_dir: Path) -> None:
    lib = recipe_dir / "lib"
    if not lib.is_dir():
        return
    for name in ("secrets.py", "llm.py", "mail.py"):
        src = GOLDEN / name
        dst = lib / name
        if src.is_file() and (not dst.is_file() or name in {"secrets.py", "llm.py", "mail.py"}):
            if name == "llm.py" and not dst.is_file():
                continue
            if name == "mail.py" and not (recipe_dir / "agent.py").read_text(encoding="utf-8").find("mail") >= 0 if (recipe_dir / "agent.py").is_file() else False:
                if not dst.is_file():
                    pass  # still copy if exists
            shutil.copy2(src, dst)


def patch_file(path: Path, replacements: list[tuple[str, str]]) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_manifest(recipe_dir: Path, slug: str) -> None:
    if slug not in RECIPE_VAULT:
        return
    path = recipe_dir / "instavm.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = RECIPE_VAULT[slug]
    hosts = spec.get("hosts") or []
    required = spec.get("required", bool(hosts))

    if hosts:
        data["vault"] = {"required": required, "hosts": hosts}
    elif "vault" in data:
        del data["vault"]

    egress_domains = spec.get("egress") or []
    if hosts or egress_domains:
        data["egress"] = {
            "mode": "allowlist",
            "include_vault_hosts": bool(hosts),
            "allowed_domains": egress_domains,
            "allow_package_managers": True,
        }
    data["secrets"] = []
    notes = data.get("post_deploy_notes") or []
    vault_note = "Run `instavm vault setup .` — upstream keys are vault placeholders injected at egress (OPENAI_KEY, EXA_KEY, etc.)."
    if notes and vault_note not in notes[0]:
        notes.insert(0, vault_note)
    data["post_deploy_notes"] = notes
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8")


def main() -> None:
    for recipe_dir in sorted(ROOT.glob("recipe-*/")):
        slug = recipe_dir.name
        lib = recipe_dir / "lib"
        if lib.is_dir():
            for name in ("secrets.py",):
                src, dst = GOLDEN / name, lib / name
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
            if (lib / "llm.py").is_file() and (GOLDEN / "llm.py").resolve() != (lib / "llm.py").resolve():
                shutil.copy2(GOLDEN / "llm.py", lib / "llm.py")
            if (lib / "mail.py").is_file() and (GOLDEN / "mail.py").resolve() != (lib / "mail.py").resolve():
                shutil.copy2(GOLDEN / "mail.py", lib / "mail.py")

        for py in list(recipe_dir.glob("integrations/**/*.py")) + list(recipe_dir.glob("lib/**/*.py")) + [recipe_dir / "agent.py"]:
            if py.is_file() and ".venv" not in str(py):
                patch_file(py, REPLACEMENTS_INTEGRATIONS)

        for cfg in recipe_dir.glob("lib/config.py"):
            patch_file(cfg, CONFIG_MOCK_DEFAULTS)

        patch_manifest(recipe_dir, slug)
        print(f"vault pattern: {slug}")


if __name__ == "__main__":
    main()
