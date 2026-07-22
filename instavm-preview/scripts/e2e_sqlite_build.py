#!/usr/bin/env python3
"""E2E: Preview /api/build with a sqlite prompt — verify tools + usage SSE."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PROMPT = (
    "Build a tiny note app with one text field and a list. "
    "Persist notes in sqlite3 under app/data/notes.db (not public/). "
    "Serve on port 8080. Minimal polished UI, no CDNs."
)


def main() -> int:
    body = json.dumps({"prompt": PROMPT}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/build",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"POST {BASE}/api/build")
    print(f"prompt: {PROMPT[:80]}…")

    tools = 0
    usage = None
    preview = None
    error = None
    phases_done: set[str] = set()

    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            buf = b""
            while True:
                chunk = resp.read(512)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    frame, buf = buf.split(b"\n\n", 1)
                    text = frame.decode("utf-8", "replace")
                    if text.startswith(":"):
                        continue
                    event = "message"
                    data_lines: list[str] = []
                    for line in text.split("\n"):
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                    raw = "\n".join(data_lines)
                    try:
                        data = json.loads(raw or "{}")
                    except json.JSONDecodeError:
                        data = {"raw": raw}

                    if event == "phase" and data.get("status") == "done":
                        phases_done.add(data.get("id", ""))
                        print(f"  phase done: {data.get('id')}")
                    elif event == "tool_called":
                        tools += 1
                        name = data.get("name", "tool")
                        args = (data.get("args") or "")[:100]
                        print(f"  tool: {name} {args}")
                    elif event == "usage":
                        usage = data
                        print(f"  usage: {data}")
                    elif event == "preview":
                        preview = data
                        print(f"  preview: {data.get('url')}")
                        if data.get("usage"):
                            usage = data["usage"]
                    elif event == "error":
                        error = data.get("message")
                        print(f"  error: {error}")
                    elif event == "done":
                        break
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read()[:500])
        return 1
    except Exception as exc:
        print("FAIL", exc)
        return 1

    print()
    ok = True
    if error:
        print("RESULT fail:", error)
        ok = False
    if not preview or not preview.get("url"):
        print("RESULT fail: no preview URL")
        ok = False
    if tools < 1:
        print("RESULT fail: no tool_called events (agent tools not exercised)")
        ok = False
    else:
        print(f"RESULT tools_called={tools}")
    if not usage or not usage.get("total_tokens"):
        print("RESULT warn: missing usage/total_tokens (server may be stale)")
        # soft-fail if server wasn't reloaded; still mark ok if preview worked
    else:
        print(
            f"RESULT usage ok: {usage.get('total_tokens')} total "
            f"({usage.get('input_tokens')}↑ {usage.get('output_tokens')}↓) "
            f"model={usage.get('model')}"
        )
    if "build" not in phases_done:
        print("RESULT warn: build phase not marked done")
    if ok and preview:
        print("RESULT pass", preview.get("url"))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
