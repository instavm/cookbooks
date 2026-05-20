#!/usr/bin/env python3
"""Copy shared lib modules from recipe-08 golden template into all recipe cookbooks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "recipe-08-hn-signal-scanner" / "lib"

# Recipes that keep a minimal LLM stub instead of the full client.
LLM_STUB_RECIPES = {
    "recipe-24-stripe-revenue-dashboard",
    "recipe-28-browser-snapshot-fork",
    "recipe-29-computer-use-replay",
    "recipe-30-mcp-server-hosting",
    "recipe-31-deterministic-replay",
}

LLM_STUB = '''"""LLM stub — not used by this recipe; included for cookbook layout consistency."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    def complete(self, system: str, user: str) -> LLMResult:
        raise NotImplementedError("This recipe does not call an LLM")

    def complete_json(self, system: str, user: str) -> dict:
        raise NotImplementedError("This recipe does not call an LLM")
'''

SYNC_FILES = ("secrets.py", "mail.py", "webhooks.py")


def main() -> None:
    for recipe_dir in sorted(ROOT.glob("recipe-*/")):
        slug = recipe_dir.name
        lib_dir = recipe_dir / "lib"
        lib_dir.mkdir(exist_ok=True)
        for name in SYNC_FILES:
            src = GOLDEN / name
            dst = lib_dir / name
            if not src.is_file() or src.resolve() == dst.resolve():
                continue
            src_bytes = src.read_bytes()
            if dst.is_file() and dst.read_bytes() == src_bytes:
                continue
            dst.write_bytes(src_bytes)
            print(f"sync {slug}/lib/{name}")
        llm_dst = lib_dir / "llm.py"
        if slug in LLM_STUB_RECIPES:
            current = llm_dst.read_text(encoding="utf-8") if llm_dst.is_file() else ""
            if current != LLM_STUB:
                llm_dst.write_text(LLM_STUB, encoding="utf-8")
                print(f"stub {slug}/lib/llm.py")
        else:
            src = GOLDEN / "llm.py"
            if src.resolve() == llm_dst.resolve():
                continue
            src_bytes = src.read_bytes()
            if llm_dst.is_file() and llm_dst.read_bytes() == src_bytes:
                continue
            llm_dst.write_bytes(src_bytes)
            print(f"sync {slug}/lib/llm.py")


if __name__ == "__main__":
    main()
