from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from agents.sandbox import Manifest
from instavm.integrations.openai_agents import (
    InstaVMSandboxClient,
    InstaVMSandboxClientOptions,
)


class SandboxClientProtocol(Protocol):
    async def create(
        self,
        *,
        snapshot: Any = None,
        manifest: Manifest | None = None,
        options: InstaVMSandboxClientOptions,
    ) -> Any: ...

    async def delete(self, session: Any) -> Any: ...


@dataclass
class ChildResult:
    task: str
    stdout: str
    exit_code: int


@dataclass
class ForkResult:
    children: list[ChildResult]
    snapshot_id: str | None = None


async def _run_echo_child(
    client: SandboxClientProtocol,
    task: str,
    *,
    snapshot_id: str | None,
    options: InstaVMSandboxClientOptions,
) -> ChildResult:
    opts = options
    if snapshot_id:
        opts = options.model_copy(update={"snapshot_id": snapshot_id})
    session = await client.create(manifest=Manifest(), options=opts)
    try:
        result = await session.exec("sh", "-c", f"echo sandbox:{task}")
        stdout = (getattr(result, "stdout", None) or "").strip()
        exit_code = int(getattr(result, "exit_code", 0) or 0)
        return ChildResult(task=task, stdout=stdout, exit_code=exit_code)
    finally:
        await client.delete(session)


async def run_parallel_fork(
    tasks: list[str],
    *,
    client: SandboxClientProtocol | None = None,
    api_key: str | None = None,
    snapshot_id: str | None = None,
) -> ForkResult:
    if not tasks:
        raise ValueError("tasks must not be empty")

    sandbox_client = client or InstaVMSandboxClient(api_key=api_key)
    options = InstaVMSandboxClientOptions(
        memory_mb=512,
        timeout=120,
        allow_internet_access=False,
        allow_package_managers=False,
    )
    children = await asyncio.gather(
        *[_run_echo_child(sandbox_client, task, snapshot_id=snapshot_id, options=options) for task in tasks]
    )
    return ForkResult(children=list(children), snapshot_id=snapshot_id)
