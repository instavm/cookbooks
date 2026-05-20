from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from lib.secrets import vault_credential


@dataclass
class MailResult:
    sent: bool
    dry_run: bool
    recipient: str
    subject: str


def send_email(*, to: str, subject: str, body: str, dry_run: bool = False) -> MailResult:
    if dry_run or os.environ.get("MAIL_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return MailResult(sent=False, dry_run=True, recipient=to, subject=subject)

    token = vault_credential("MAILTRAP_API_TOKEN")
    host = os.environ.get("MAILTRAP_HOST", "sandbox.smtp.mailtrap.io")
    port = int(os.environ.get("MAILTRAP_PORT", "2525"))
    user = os.environ.get("MAILTRAP_USER") or token
    password = os.environ.get("MAILTRAP_PASSWORD") or token

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_FROM", "cookbook@instavm.io")
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)

    return MailResult(sent=True, dry_run=False, recipient=to, subject=subject)
