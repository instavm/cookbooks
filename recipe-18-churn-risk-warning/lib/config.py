from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fixtures_dir() -> Path:
    return Path(os.environ.get("FIXTURES_DIR", ROOT / "fixtures"))


def stripe_fixture() -> Path:
    return fixtures_dir() / "stripe_subs.json"


def intercom_fixture() -> Path:
    return fixtures_dir() / "intercom_sentiment.json"


ALERT_TO = os.environ.get("ALERT_TO", os.environ.get("DIGEST_TO", "you@example.com"))
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
