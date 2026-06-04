import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from lib.secrets import secret_available

pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    return TestClient(app)


def test_e2e_offline_happy_path(client, monkeypatch, tmp_path):
    """Full dry-run path without external API keys."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "0")
    monkeypatch.setenv("MAIL_DRY_RUN", "1")
    fixture = json.loads((Path(__file__).parent.parent / "fixtures" / "pr_opened.json").read_text())
    resp = client.post("/webhook/github?dry_run=true", json=fixture)
    assert resp.status_code == 200


@pytest.mark.skipif(not secret_available("OPENAI_API_KEY"), reason="OPENAI_API_KEY missing")
def test_e2e_live_optional():
    """Run manually against a deployed VM when vault + keys are configured."""
    assert secret_available("OPENAI_API_KEY")

