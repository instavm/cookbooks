"""Linkup account news — mock-friendly HTTP client."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

LINKUP_URL = "https://api.linkup.so/v1/search"


@dataclass(frozen=True)
class AccountNews:
    domain: str
    answer: str
    fingerprint: str


def _mock_news(domain: str) -> AccountNews:
    answer = f"[mock] Recent news for {domain}: product launch and hiring update."
    return AccountNews(domain=domain, answer=answer, fingerprint=hashlib.sha256(answer.encode()).hexdigest()[:16])


def fetch_account_news(domain: str, *, client: httpx.Client | None = None) -> AccountNews:
    if mock_enabled("LINKUP_MOCK") or mock_enabled("LINKUP_TEST_MODE"):
        return _mock_news(domain)

    key = vault_credential("LINKUP_API_KEY")
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(
            LINKUP_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "q": f'site:{domain} OR "{domain}" news 2026',
                "depth": "standard",
                "outputType": "sourcedAnswer",
            },
        )
        resp.raise_for_status()
        answer = str(resp.json().get("answer") or resp.json().get("content") or "")
    finally:
        if owns_client:
            http.close()
    fingerprint = hashlib.sha256(answer.encode()).hexdigest()[:16]
    return AccountNews(domain=domain, answer=answer, fingerprint=fingerprint)
