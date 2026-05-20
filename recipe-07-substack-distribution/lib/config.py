from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def ledger_path() -> Path:
    return data_dir() / "distributed_ledger.json"


def preview_path() -> Path:
    return data_dir() / "preview.html"


def drafts_path() -> Path:
    return data_dir() / "drafts.json"
