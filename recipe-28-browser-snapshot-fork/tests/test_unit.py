from __future__ import annotations

import pytest

from lib.sandbox_fork import run_parallel_fork


class _FakeExecResult:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.exit_code = 0


class _FakeSession:
    def __init__(self, task: str) -> None:
        self._task = task

    async def exec(self, *args, **kwargs):
        return _FakeExecResult(f"sandbox:{self._task}")


class _FakeInstaVMSandboxClient:
    def __init__(self, **kwargs) -> None:
        self.created = 0

    async def create(self, **kwargs):
        self.created += 1
        task = f"fork-{self.created}"
        return _FakeSession(task)

    async def delete(self, session):
        return session


@pytest.mark.asyncio
async def test_run_parallel_fork_mock():
    client = _FakeInstaVMSandboxClient()
    result = await run_parallel_fork(["alpha", "beta"], client=client)
    assert len(result.children) == 2
    assert all(c.exit_code == 0 for c in result.children)
    assert client.created == 2
