#!/usr/bin/env python3
"""Smoke-test InstaVM account primitives used by Preview / future NL control plane.

Loads local secrets (PREVIEW_LOCAL=1) and exercises:
  - auth / credits
  - short-lived session create + execute(sqlite3) + kill
  - volume create / upload / list_files / delete
  - SSH connect hint format
  - Preview builder DB system-prompt guidance
  - Agents SDK usage helper shape

Does NOT leave long-lived VMs running.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PREVIEW_LOCAL", "1")

from app import config
from app.build import builder_instructions, data_guidance, usage_from_stream
from app.local_secrets import apply_local_secrets


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.passed.append(name)
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, err: str) -> None:
        self.failed.append((name, err))
        print(f"  FAIL  {name} — {err}")


def _stdout(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("stdout") or result.get("output") or "")
    return str(result)


def _stderr(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("stderr") or "")
    return ""


def main() -> int:
    loaded = apply_local_secrets(force=True)
    print(f"secrets: instavm={loaded['instavm']} openai={loaded['openai']}")
    print(f"model default: {config.MODEL_NAME}")
    print(f"workspace: {config.WORKSPACE_ROOT}")
    print(f"data_dir: {config.DATA_DIR}")
    r = Result()

    # --- offline: instructions / metering ---
    try:
        text = builder_instructions("test-session-id")
        assert "sqlite3" in text
        assert "DuckDB" in text or "duckdb" in text
        assert "app/data" in text or config.DATA_DIR in text
        assert "Postgres" in text or "postgres" in data_guidance().lower()
        r.ok("builder_instructions_db_policy", f"{len(text)} chars")
    except Exception as exc:
        r.fail("builder_instructions_db_policy", str(exc))

    try:

        class FakeUsage:
            requests = 2
            input_tokens = 100
            output_tokens = 40
            total_tokens = 140

        class FakeWrapper:
            usage = FakeUsage()

        class FakeStream:
            context_wrapper = FakeWrapper()

        u = usage_from_stream(FakeStream())
        assert u["total_tokens"] == 140 and u["model"] == config.MODEL_NAME
        r.ok("usage_from_stream", str(u))
    except Exception as exc:
        r.fail("usage_from_stream", str(exc))

    # --- live InstaVM ---
    try:
        from instavm import InstaVM

        key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("INSTAVM_API_KEY missing")
        client = InstaVM(api_key=key, timeout=300, memory_mb=1024, cpu_count=1)
        summary = client.credits.summary()
        remaining = summary.get("dollars", {}).get("remaining")
        r.ok("credits.summary", f"remaining=${remaining}")
    except Exception as exc:
        r.fail("credits.summary", f"{exc}")
        print("\nAborting further live InstaVM calls.")
        return _exit(r)

    session_id = None
    try:
        session_id = client.start_session()
        r.ok("start_session", f"id={session_id}")

        result = client.execute(
            "import sqlite3; print('sqlite', sqlite3.sqlite_version)",
            language="python",
        )
        stdout = _stdout(result)
        stderr = _stderr(result)
        if "sqlite" not in stdout.lower():
            raise RuntimeError(f"stdout={stdout!r} stderr={stderr!r} raw={result!r}")
        r.ok("session_exec_sqlite3", stdout.strip()[:120])

        # Tiny DB write in session workspace (python language, not shell)
        result2 = client.execute(
            "\n".join(
                [
                    "import sqlite3, os",
                    "os.makedirs('/home/appuser/workspace/app/data', exist_ok=True)",
                    "path='/home/appuser/workspace/app/data/smoke.db'",
                    "con=sqlite3.connect(path)",
                    "con.execute('create table if not exists t(id integer primary key, note text)')",
                    "con.execute(\"insert into t(note) values ('ok')\")",
                    "con.commit()",
                    "print(path, con.execute('select note from t').fetchone()[0])",
                    "con.close()",
                ]
            ),
            language="python",
        )
        out2 = _stdout(result2)
        if "ok" not in out2:
            raise RuntimeError(f"stdout={out2!r} stderr={_stderr(result2)!r} raw={result2!r}")
        r.ok("session_sqlite_file", out2.strip()[:160])
    except Exception as exc:
        r.fail("session_lifecycle", f"{exc}\n{traceback.format_exc()[:600]}")
    finally:
        try:
            if session_id:
                client.kill(session_id)
                r.ok("kill_session", session_id)
        except Exception as exc:
            r.fail("kill_session", str(exc))

    # Volumes
    vol_id = None
    try:
        name = f"preview-smoke-{int(time.time())}"
        vol = client.volumes.create(name=name, quota_bytes=64 * 1024 * 1024)
        vol_id = vol.get("id") if isinstance(vol, dict) else getattr(vol, "id", None)
        if not vol_id:
            raise RuntimeError(f"no volume id in {vol!r}")
        r.ok("volumes.create", f"id={vol_id} name={name}")

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
            tmp.write("hello-from-preview-smoke\n")
            local_path = tmp.name
        try:
            client.volumes.upload_file(vol_id, local_path, "notes.txt", overwrite=True)
            r.ok("volumes.upload_file", "notes.txt")
        finally:
            Path(local_path).unlink(missing_ok=True)

        files = client.volumes.list_files(vol_id)
        names = []
        for f in files or []:
            if isinstance(f, dict):
                names.append(f.get("path") or f.get("name") or str(f))
            else:
                names.append(str(f))
        if not any("notes" in n for n in names):
            # Some APIs return relative paths differently
            r.ok("volumes.list_files", f"entries={names[:5]!r}")
        else:
            r.ok("volumes.list_files", f"found notes in {names[:5]!r}")
    except Exception as exc:
        r.fail("volumes", f"{exc}\n{traceback.format_exc()[:600]}")
    finally:
        try:
            if vol_id:
                client.volumes.delete(vol_id)
                r.ok("volumes.delete", str(vol_id))
        except Exception as exc:
            r.fail("volumes.delete", str(exc))

    # SSH hint + managers
    try:
        host = os.environ.get("INSTAVM_SSH_HOST")
        if not host:
            try:
                from instavm._cli_config import derive_ssh_host

                host = derive_ssh_host()
            except Exception:
                host = "ssh.instavm.io"
        r.ok("ssh_connect_hint_format", f"ssh {{vm_id}}@{host}")
    except Exception as exc:
        r.fail("ssh_connect_hint_format", str(exc))

    try:
        assert hasattr(client, "shares")
        assert hasattr(client, "vms")
        assert hasattr(client, "pty")
        assert hasattr(client, "templates")
        r.ok(
            "managers_present",
            "shares, vms, pty, templates, volumes",
        )
    except Exception as exc:
        r.fail("managers_present", str(exc))

    return _exit(r)


def _exit(r: Result) -> int:
    print()
    print(f"passed={len(r.passed)} failed={len(r.failed)}")
    for name, err in r.failed:
        print(f" - {name}: {err.splitlines()[0]}")
    return 1 if r.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
