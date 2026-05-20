from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from lib.config import NOTION_DATABASE_ID
from lib.secrets import mock_enabled, vault_credential

NOTION_PAGES = "https://api.notion.com/v1/pages"


@dataclass
class NotionAppendResult:
    appended: int
    page_ids: list[str]
    dry_run: bool


def append_roadmap_items(
    items: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> NotionAppendResult:
    if dry_run:
        return NotionAppendResult(appended=0, page_ids=[], dry_run=True)

    if mock_enabled("NOTION_MOCK"):
        return NotionAppendResult(
            appended=len(items),
            page_ids=[f"mock-page-{i}" for i, _ in enumerate(items)],
            dry_run=False,
        )

    token = vault_credential("NOTION_TOKEN") or os.environ.get("NOTION_TOKEN", "")
    http = client or httpx.Client(timeout=30.0)
    page_ids: list[str] = []
    for item in items:
        resp = http.post(
            NOTION_PAGES,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": str(item.get("title", "Untitled"))}}]},
                    "Priority": {"select": {"name": str(item.get("priority", "Medium"))}},
                },
            },
        )
        resp.raise_for_status()
        page_ids.append(resp.json().get("id", ""))
    return NotionAppendResult(appended=len(page_ids), page_ids=page_ids, dry_run=False)
