"""ABM daily monitor — Linkup news, diff store, Mailtrap digest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from integrations.linkup import fetch_account_news
from lib.config import DIGEST_TO, accounts_file, load_accounts_from_env, seen_hashes_path
from lib.diff_store import FingerprintStore
from lib.mail import send_email


@dataclass
class MonitorResult:
    accounts_checked: int
    new_signal: int
    digest: str
    mail_sent: bool
    dry_run: bool


def resolve_accounts(accounts: list[str] | None = None) -> list[str]:
    if accounts:
        return accounts
    env_accounts = load_accounts_from_env()
    if env_accounts:
        return env_accounts
    path = accounts_file()
    if path.is_file():
        return [str(x) for x in json.loads(path.read_text(encoding="utf-8"))]
    return []


def save_accounts(accounts: list[str], path: Path | None = None) -> Path:
    dest = path or accounts_file()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    return dest


def run_monitor(
    *,
    accounts: list[str] | None = None,
    dry_run: bool = False,
    http: httpx.Client | None = None,
) -> MonitorResult:
    domains = resolve_accounts(accounts)
    if not domains:
        return MonitorResult(
            accounts_checked=0,
            new_signal=0,
            digest="No accounts configured.",
            mail_sent=False,
            dry_run=dry_run,
        )

    store = FingerprintStore(seen_hashes_path())
    digest_lines: list[str] = []

    for domain in domains:
        news = fetch_account_news(domain, client=http)
        if not news.answer:
            continue
        if not store.is_new(domain, news.fingerprint):
            continue
        digest_lines.append(f"**{domain}**: {news.answer[:300]}")
        if not dry_run:
            store.set(domain, news.fingerprint)

    if not dry_run and digest_lines:
        store.flush()

    digest = "\n\n".join(digest_lines) if digest_lines else "No new ABM signal today."
    mail_sent = False
    if digest_lines and not dry_run:
        mail = send_email(
            to=DIGEST_TO,
            subject=f"ABM signal digest — {len(digest_lines)} accounts",
            body=digest,
            dry_run=False,
        )
        mail_sent = mail.sent

    return MonitorResult(
        accounts_checked=len(domains),
        new_signal=len(digest_lines),
        digest=digest,
        mail_sent=mail_sent,
        dry_run=dry_run,
    )
