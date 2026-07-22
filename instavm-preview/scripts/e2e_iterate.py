#!/usr/bin/env python3
"""E2E: build → follow-up iterate → verify HTML changed on the live preview."""

from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

BUILD_PROMPT = (
    "Create /home/appuser/workspace/app/public/index.html as a complete HTML page "
    "with an <h1> whose text is exactly Alpha Title, centered on white. "
    "Include the required InstaVM Preview footer. Serve with "
    "`python3 -m http.server 8080 --directory /home/appuser/workspace/app/public`. "
    "Do not leave the public folder empty."
)

ITERATE_INSTRUCTION = (
    "Change the main <h1> text to exactly 'Beta Revised' and add a subtitle "
    "paragraph that says exactly 'iterate-ok'. Keep the footer. Restart if needed."
)


def read_sse(resp) -> dict:
    tools = 0
    usage = None
    preview = None
    error = None
    phases_done: set[str] = set()
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
                args = (data.get("args") or "")[:120]
                print(f"  tool: {name} {args}")
            elif event == "usage":
                usage = data
                print(f"  usage: total={data.get('total_tokens')}")
            elif event == "preview":
                preview = data
                print(f"  preview: {data.get('url')} session={data.get('session_id')}")
            elif event == "error":
                error = data.get("message")
                print(f"  error: {error}")
            elif event == "done":
                return {
                    "tools": tools,
                    "usage": usage,
                    "preview": preview,
                    "error": error,
                    "phases_done": phases_done,
                }
    return {
        "tools": tools,
        "usage": usage,
        "preview": preview,
        "error": error,
        "phases_done": phases_done,
    }


def fetch_html(url: str, attempts: int = 8) -> str:
    last_err: Exception | None = None
    for i in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": "instavm-preview-e2e"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 — retry share warm-up / 502
            last_err = exc
            print(f"  fetch retry {i + 1}/{attempts}: {exc}")
            time.sleep(1.5 + i * 0.5)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def main() -> int:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    print(f"1) BUILD  {BASE}/api/build")
    body = json.dumps({"prompt": BUILD_PROMPT}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/build",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=360) as resp:
            build = read_sse(resp)
    except urllib.error.HTTPError as exc:
        print("BUILD HTTP", exc.code, exc.read()[:500])
        return 1
    except Exception as exc:
        print("BUILD FAIL", exc)
        return 1

    if build["error"] or not build["preview"] or not build["preview"].get("url"):
        print("BUILD RESULT fail", build.get("error"))
        return 1
    if build["tools"] < 1:
        print("BUILD RESULT fail: no tools")
        return 1

    url = build["preview"]["url"]
    session_id = build["preview"]["session_id"]
    print(f"\n2) VERIFY initial HTML at {url}")
    html = fetch_html(url)
    if "Alpha Title" not in html:
        print("BUILD verify fail: missing 'Alpha Title'")
        print(html[:500])
        return 1
    print("  found Alpha Title")

    # guest cookie from jar
    guest = None
    for c in jar:
        if c.name == "ivm_preview_guest":
            guest = c.value
    print(f"  guest_cookie={guest!r} session={session_id}")

    print(f"\n3) ITERATE  {BASE}/api/iterate")
    body = json.dumps(
        {
            "session_id": session_id,
            "instruction": ITERATE_INSTRUCTION,
            "guest_id": guest,
        }
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/api/iterate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=360) as resp:
            it = read_sse(resp)
    except urllib.error.HTTPError as exc:
        print("ITERATE HTTP", exc.code, exc.read()[:500])
        return 1
    except Exception as exc:
        print("ITERATE FAIL", exc)
        return 1

    if it["error"]:
        print("ITERATE RESULT fail", it["error"])
        return 1
    if it["tools"] < 1:
        print("ITERATE RESULT fail: no tools")
        return 1
    if not it["preview"] or not it["preview"].get("url"):
        print("ITERATE RESULT fail: no preview")
        return 1

    preview_url = it["preview"]["url"]
    print(f"\n4) VERIFY revised HTML at {preview_url}")
    time.sleep(2)
    html2 = fetch_html(preview_url + ("&" if "?" in preview_url else "?") + f"_e2e={int(time.time())}")
    ok_beta = "Beta Revised" in html2
    ok_marker = "iterate-ok" in html2
    still_alpha = "Alpha Title" in html2 and "Beta Revised" not in html2

    print(f"  Beta Revised: {ok_beta}")
    print(f"  iterate-ok:   {ok_marker}")
    print(f"  stuck Alpha:  {still_alpha}")
    if it.get("usage"):
        print(f"  iterate usage: {it['usage'].get('total_tokens')} tokens")

    if ok_beta and ok_marker and not still_alpha:
        print("\nRESULT pass — follow-up revise applied")
        return 0

    print("\nRESULT fail — revision not reflected in preview HTML")
    # show h1-ish snippet
    m = re.search(r"<h1[^>]*>.*?</h1>", html2, re.I | re.S)
    print("  h1:", (m.group(0) if m else html2[:400]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
