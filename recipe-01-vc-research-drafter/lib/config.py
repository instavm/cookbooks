from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def contacted_path() -> Path:
    return data_dir() / "contacted_vcs.json"


DRAFT_TO = os.environ.get("DRAFT_TO", "you@example.com")
VC_THESIS = os.environ.get("VC_THESIS", "developer tools AI infrastructure B2B SaaS")
COMPANY_BLURB = os.environ.get(
    "COMPANY_BLURB",
    "We build AI infrastructure for founders. $500K ARR, 3 enterprise pilots.",
)
MAX_VCS = int(os.environ.get("MAX_VCS", "20"))
MAX_DRAFTS_PER_RUN = int(os.environ.get("MAX_DRAFTS_PER_RUN", "5"))
