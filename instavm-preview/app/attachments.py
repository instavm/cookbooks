"""Validate and normalize image attachments for vision builds."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from typing import Any

from . import config

_DATA_URL_RE = re.compile(
    r"^data:(?P<mime>image/(?:png|jpeg|jpg|webp|gif));base64,(?P<data>.+)$",
    re.IGNORECASE | re.DOTALL,
)

_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


@dataclass(frozen=True)
class Attachment:
    name: str
    mime_type: str
    data: bytes

    @property
    def data_url(self) -> str:
        b64 = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{b64}"

    @property
    def safe_filename(self) -> str:
        base = re.sub(r"[^A-Za-z0-9._-]+", "-", (self.name or "reference").strip())
        base = base.strip(".-") or "reference"
        if "." not in base:
            base = f"{base}.{_EXT.get(self.mime_type, 'png')}"
        return base[:80]


def _normalize_mime(mime: str) -> str:
    mime = (mime or "").strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    return mime


def _decode_payload(raw: str) -> bytes:
    cleaned = "".join(raw.split())
    try:
        return base64.b64decode(cleaned, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 image data.") from exc


def parse_attachments(raw_items: list[Any] | None) -> list[Attachment]:
    if not raw_items:
        return []
    if len(raw_items) > config.MAX_ATTACHMENTS:
        raise ValueError(
            f"At most {config.MAX_ATTACHMENTS} attachments allowed."
        )

    out: list[Attachment] = []
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"Attachment {i + 1} must be an object.")

        name = str(item.get("name") or f"reference-{i + 1}").strip()[:120]
        mime = _normalize_mime(str(item.get("mime_type") or item.get("mimeType") or ""))
        data_b64 = item.get("data_base64") or item.get("dataBase64") or ""
        data_url = item.get("data_url") or item.get("dataUrl") or ""

        if data_url:
            match = _DATA_URL_RE.match(str(data_url).strip())
            if not match:
                raise ValueError(
                    f"Attachment {i + 1}: only image data URLs are supported "
                    "(png, jpeg, webp, gif)."
                )
            mime = _normalize_mime(match.group("mime"))
            data = _decode_payload(match.group("data"))
        elif data_b64:
            if mime not in config.ALLOWED_ATTACHMENT_MIMES:
                raise ValueError(
                    f"Attachment {i + 1}: unsupported type {mime or '(missing)'}."
                )
            data = _decode_payload(str(data_b64))
        else:
            raise ValueError(f"Attachment {i + 1}: missing image data.")

        if mime not in config.ALLOWED_ATTACHMENT_MIMES:
            raise ValueError(f"Attachment {i + 1}: unsupported type {mime}.")
        if not data:
            raise ValueError(f"Attachment {i + 1}: empty file.")
        if len(data) > config.MAX_ATTACHMENT_BYTES:
            mb = config.MAX_ATTACHMENT_BYTES // (1024 * 1024)
            raise ValueError(
                f"Attachment {i + 1}: larger than {mb}MB limit."
            )

        out.append(Attachment(name=name, mime_type=mime, data=data))
    return out


def agent_input(prompt: str, attachments: list[Attachment]) -> str | list[dict[str, Any]]:
    """Build Runner input: plain string, or multimodal user message."""
    text = prompt.strip()
    if not attachments:
        return text

    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": text},
    ]
    for att in attachments:
        content.append(
            {
                "type": "input_image",
                "image_url": att.data_url,
                "detail": "high",
            }
        )
    return [{"role": "user", "content": content}]


def reference_paths(attachments: list[Attachment]) -> list[str]:
    root = config.WORKSPACE_ROOT
    return [
        f"{root}/app/reference/{i + 1:02d}-{att.safe_filename}"
        for i, att in enumerate(attachments)
    ]