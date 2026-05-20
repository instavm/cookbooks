"""Lost deal post-mortem — transcript to structured LLM JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from lib.llm import LLMClient

POSTMORTEM_SYSTEM = """You analyze lost sales call transcripts.
Return JSON only with this schema:
{
  "deal_name": "string",
  "loss_reason": "primary reason",
  "competitor": "name or null",
  "objections": ["list of buyer objections"],
  "what_went_well": ["list"],
  "what_to_improve": ["list"],
  "recommended_actions": ["list of concrete next steps"],
  "confidence": 0.0-1.0
}"""


@dataclass
class PostmortemResult:
    postmortem: dict[str, Any]
    dry_run: bool


def analyze_transcript(
    transcript: str,
    *,
    deal_name: str = "",
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> PostmortemResult:
    if dry_run:
        return PostmortemResult(
            postmortem={
                "deal_name": deal_name or "Unknown",
                "loss_reason": "Dry run — LLM skipped",
                "competitor": None,
                "objections": [],
                "what_went_well": [],
                "what_to_improve": [],
                "recommended_actions": [],
                "confidence": 0.0,
            },
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    user = f"Deal: {deal_name or 'Unknown'}\n\nTranscript:\n{transcript[:12000]}"
    postmortem = client.complete_json(POSTMORTEM_SYSTEM, user)
    if deal_name and not postmortem.get("deal_name"):
        postmortem["deal_name"] = deal_name
    return PostmortemResult(postmortem=postmortem, dry_run=False)
