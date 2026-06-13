"""Reusable fakes for the worker microVM lifecycle."""

from __future__ import annotations

from typing import Any


class FakeWorkerClient:
    """Stand-in for an InstaVM session that records lifecycle calls."""

    instances: list["FakeWorkerClient"] = []

    def __init__(self, *, api_key: str | None, memory_mb: int, cpu_count: int,
                 env: dict[str, str], metadata: dict[str, str]) -> None:
        self.api_key = api_key
        self.memory_mb = memory_mb
        self.cpu_count = cpu_count
        self.env = env
        self.metadata = metadata
        self.session_id = f"vm-{len(FakeWorkerClient.instances) + 1}"
        self.egress: dict[str, Any] | None = None
        self.commands: list[str] = []
        self.closed = False
        FakeWorkerClient.instances.append(self)

    def set_session_egress(self, *, allow_package_managers: bool = True,
                           allowed_domains: list[str] | None = None) -> dict[str, Any]:
        self.egress = {
            "allow_package_managers": allow_package_managers,
            "allowed_domains": list(allowed_domains or []),
        }
        return self.egress

    def execute_async(self, command: str, language: str | None = None,
                      timeout: int | None = None) -> dict[str, Any]:
        self.commands.append(command)
        return {"task_id": f"task-{self.session_id}"}

    def close_session(self) -> bool:
        self.closed = True
        return True


def fake_factory(**kwargs: Any) -> FakeWorkerClient:
    return FakeWorkerClient(**kwargs)
