from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def seen_hashes_path() -> Path:
    return data_dir() / "seen_hashes.json"


def accounts_file() -> Path:
    return Path(os.environ.get("ACCOUNTS_FILE", str(data_dir() / "accounts.json")))


def load_accounts_from_env() -> list[str]:
    raw = os.environ.get("ABM_ACCOUNTS", "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        return [str(x) for x in json.loads(raw)]
    return [part.strip() for part in raw.split(",") if part.strip()]


DIGEST_TO = os.environ.get("DIGEST_TO", "you@example.com")
