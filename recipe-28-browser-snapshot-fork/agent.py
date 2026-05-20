"""Fork authenticated browser snapshot into parallel child sandboxes."""

from __future__ import annotations

from dataclasses import dataclass

from lib.config import DEFAULT_TASKS, PARALLEL_CHILDREN
from lib.sandbox_fork import ChildResult, ForkResult, run_parallel_fork
from lib.secrets import mock_enabled, vault_credential


async def run_fork(
    tasks: list[str] | None = None,
    *,
    snapshot_id: str | None = None,
    client=None,
) -> ForkResult:
    chosen = list(tasks or DEFAULT_TASKS)[:PARALLEL_CHILDREN]
    if mock_enabled("INSTAVM_FORK_MOCK"):
        return ForkResult(
            children=[ChildResult(task=t, stdout=f"sandbox:{t}", exit_code=0) for t in chosen],
            snapshot_id=snapshot_id,
        )
    api_key = vault_credential("INSTAVM_API_KEY")
    if client is None and not api_key:
        raise RuntimeError("INSTAVM_API_KEY is required to spawn child sandboxes")
    return await run_parallel_fork(
        chosen,
        client=client,
        api_key=api_key or None,
        snapshot_id=snapshot_id,
    )
