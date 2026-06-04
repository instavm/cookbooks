from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def seen_path() -> Path:
    return data_dir() / "seen_patents.json"


DIGEST_TO = os.environ.get("DIGEST_TO", "you@example.com")
PATENT_QUERY = os.environ.get("PATENT_QUERY", "agent sandbox VM orchestration")
USE_EXA_MOCK = os.environ.get("EXA_MOCK", "").lower() in {"1", "true", "yes"}
USE_FIRECRAWL_MOCK = os.environ.get("FIRECRAWL_MOCK", "").lower() in {"1", "true", "yes"}
