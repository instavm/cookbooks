from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def titles_cache_path() -> Path:
    return data_dir() / "competitor_titles.json"


DEFAULT_COMPETITORS = [
    {"name": "E2B", "url": "https://e2b.dev/changelog"},
    {"name": "Modal", "url": "https://modal.com/blog"},
    {"name": "Daytona", "url": "https://daytona.io/blog"},
]


def competitor_list() -> list[dict[str, str]]:
    raw = os.environ.get("COMPETITOR_URLS", "")
    if not raw.strip():
        return DEFAULT_COMPETITORS
    parsed = json.loads(raw)
    return [{"name": c["name"], "url": c["url"]} for c in parsed]
