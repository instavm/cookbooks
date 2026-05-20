#!/usr/bin/env python3
"""Verify all recipe-* cookbooks against the 29-recipe implementation plan."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "instavm.yaml",
    "Dockerfile",
    "requirements.txt",
    "app.py",
    "agent.py",
    "README.md",
    "lib/__init__.py",
    "lib/secrets.py",
    "lib/config.py",
    "tests/conftest.py",
    "tests/test_unit.py",
    "tests/test_smoke.py",
    "tests/test_e2e.py",
    "tests/test_ui.py",
)

# lib/llm.py required for LLM recipes; showcase recipes may use a stub file.
LLM_OPTIONAL = {
    "recipe-24-stripe-revenue-dashboard",
    "recipe-28-browser-snapshot-fork",
    "recipe-29-computer-use-replay",
    "recipe-30-mcp-server-hosting",
    "recipe-31-deterministic-replay",
}

# Recipe number -> (primary route method+path fragment, agent hint)
RECIPE_MVPS: dict[str, tuple[str, str]] = {
    "01": ("/run", "exa"),
    "02": ("/run", "competitor"),
    "03": ("/webhook/cal", "briefing"),
    "04": ("/webhook/transcript", "follow"),
    "05": ("/webhook/email-signal", "crm"),
    "06": ("/run", "stripe"),
    "07": ("/publish", "firecrawl"),
    "08": ("/run", "hn"),
    "09": ("/run", "mention"),
    "11": ("/run", "linkup"),
    "12": ("/webhook/slack", "linear"),
    "13": ("/prospect", "exa"),
    "14": ("/run", "linkup"),
    "15": ("/transcript", "post"),
    "16": ("/topic", "seo"),
    "17": ("/transcript", "show"),
    "18": ("/scan", "churn"),
    "19": ("/run", "stripe"),
    "20": ("/webhook/transcript", "notion"),
    "21": ("/run", "standup"),
    "22": ("/webhook/github", "review"),
    "23": ("/run", "patent"),
    "24": ("/", "stripe"),
    "28": ("/fork", "fork"),
    "29": ("/capture", "frame"),
    "30": ("/health", "mcp"),
    "31": ("/replay", "replay"),
}


def recipe_num(slug: str) -> str | None:
    m = re.match(r"recipe-(\d+)-", slug)
    return m.group(1) if m else None


def check_manifest(path: Path, slug: str, errors: list[str], warnings: list[str]) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 2:
        errors.append(f"{slug}: schema_version must be 2")
    if data.get("kind", "service") != "service":
        errors.append(f"{slug}: kind must be service (cron deploy unsupported)")
    deploy = data.get("deploy") or {}
    if deploy.get("kind") != "upload_and_run":
        errors.append(f"{slug}: deploy.kind must be upload_and_run")
    source = data.get("source") or {}
    include = source.get("include") or []
    for item in include:
        if isinstance(item, str) and ("../" in item or item.startswith("/")):
            errors.append(f"{slug}: source.include must not reference paths outside project: {item}")
    exclude = source.get("exclude") or []
    for must in ("tests/", "fixtures/", ".pytest_cache/"):
        if must not in exclude:
            warnings.append(f"{slug}: source.exclude missing {must!r}")
    vault = data.get("vault") or {}
    if not vault.get("required"):
        warnings.append(f"{slug}: vault.required is not true")
    egress = data.get("egress") or {}
    if egress.get("mode") != "allowlist":
        warnings.append(f"{slug}: egress.mode is not allowlist")
    req = path.parent / "requirements.txt"
    if req.is_file():
        text = req.read_text(encoding="utf-8")
        if "instavm" not in text:
            errors.append(f"{slug}: requirements.txt missing instavm")
    llm = path.parent / "lib" / "llm.py"
    if slug not in LLM_OPTIONAL:
        if not llm.is_file():
            errors.append(f"{slug}: missing lib/llm.py")
        else:
            llm_text = llm.read_text(encoding="utf-8")
            for needle in ("LLM_PROVIDER", "openai", "anthropic"):
                if needle.lower() not in llm_text.lower():
                    errors.append(f"{slug}: lib/llm.py missing {needle!r} pattern")
    elif not llm.is_file():
        warnings.append(f"{slug}: lib/llm.py stub recommended for layout consistency")
    app = path.parent / "app.py"
    agent_path = path.parent / "agent.py"
    if app.is_file():
        app_text = app.read_text(encoding="utf-8")
        if '"/health"' not in app_text and '@app.get("/health")' not in app_text:
            errors.append(f"{slug}: app.py missing /health route")
    num = recipe_num(slug)
    if num and num in RECIPE_MVPS:
        route, hint = RECIPE_MVPS[num]
        combined = app.read_text(encoding="utf-8") if app.is_file() else ""
        if agent_path.is_file():
            combined += agent_path.read_text(encoding="utf-8")
        if route not in combined:
            errors.append(f"{slug}: missing MVP route {route}")
        if hint.lower() not in combined.lower():
            warnings.append(f"{slug}: agent may not implement MVP hint {hint!r}")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    recipes = sorted(p for p in ROOT.glob("recipe-*/") if p.is_dir())
    expected_nums = {
        f"{n:02d}"
        for n in list(range(1, 10)) + list(range(11, 25)) + [28, 29, 30, 31]
    }
    found_nums: set[str] = set()

    for recipe_dir in recipes:
        slug = recipe_dir.name
        num = recipe_num(slug)
        if num:
            found_nums.add(num)
        for rel in REQUIRED_FILES:
            if not (recipe_dir / rel).is_file():
                errors.append(f"{slug}: missing {rel}")
        check_manifest(recipe_dir / "instavm.yaml", slug, errors, warnings)

    missing = sorted(expected_nums - found_nums)
    extra = sorted(found_nums - expected_nums)
    if missing:
        errors.append(f"Missing recipe numbers: {', '.join(missing)}")
    if extra:
        errors.append(f"Unexpected recipe numbers: {', '.join(extra)}")

    # No repo-level cookbook_lib
    if (ROOT / "cookbook_lib").exists():
        errors.append("repo-level cookbook_lib/ must not exist")

    print(f"Checked {len(recipes)} recipe directories.")
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print("\nSpec verification passed.")
    if warnings:
        print(f"({len(warnings)} non-blocking warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
