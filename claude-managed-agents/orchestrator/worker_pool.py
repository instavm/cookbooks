"""Spawn and track per-session worker microVMs on InstaVM.

Each Claude Managed Agents session gets its own short-lived InstaVM microVM that
runs ``ant beta:worker poll``. The worker claims the session's queued work from
Anthropic's environment queue, downloads skills, executes the agent's tool calls
inside the isolated VM, posts results back, and exits once the session goes idle.

Provider credentials (the Anthropic environment key, plus any third-party API
keys the agent needs) are injected at the egress boundary from the InstaVM org
vault — they are never written into the worker VM. The VM only ever carries
placeholder strings.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from orchestrator.config import WorkerConfig

_log = logging.getLogger(__name__)


class WorkerClient(Protocol):
    """The subset of the InstaVM SDK session API the pool relies on."""

    def set_session_egress(self, *, allow_package_managers: bool = ..., allowed_domains: list[str] = ...) -> Any: ...

    def execute_async(self, command: str, language: str | None = ..., timeout: int | None = ...) -> Any: ...

    def close_session(self) -> Any: ...


ClientFactory = Callable[..., WorkerClient]


def _default_client_factory(*, api_key: str | None, memory_mb: int, cpu_count: int,
                            env: dict[str, str], metadata: dict[str, str]) -> WorkerClient:
    from instavm import InstaVM

    return InstaVM(
        api_key=api_key,
        memory_mb=memory_mb,
        cpu_count=cpu_count,
        env=env,
        metadata=metadata,
        auto_start_session=True,
    )


def build_worker_command(config: WorkerConfig) -> str:
    """Shell command that installs the ant CLI (if needed) and runs the poller.

    The poller reads ``ANTHROPIC_ENVIRONMENT_ID`` / ``ANTHROPIC_ENVIRONMENT_KEY``
    from the VM environment. The key is a vault placeholder in production; the
    egress proxy substitutes the real value on outbound api.anthropic.com calls.
    """
    ver = config.ant_version
    return (
        "set -e\n"
        f'mkdir -p "{config.workdir}"\n'
        'if ! command -v ant >/dev/null 2>&1; then\n'
        '  ARCH=$(uname -m | sed -e "s/x86_64/amd64/" -e "s/aarch64/arm64/");\n'
        f'  curl -fsSL "https://github.com/anthropics/anthropic-cli/releases/download/v{ver}/ant_{ver}_linux_${{ARCH}}.tar.gz"'
        ' | tar -xz -C /usr/local/bin ant;\n'
        'fi\n'
        f'exec ant beta:worker poll --workdir "{config.workdir}" --max-idle "{config.max_idle}"\n'
    )


@dataclass
class WorkerInfo:
    session_id: str
    status: str = "starting"
    created_at: float = field(default_factory=time.time)
    vm_id: str | None = None
    task_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "vm_id": self.vm_id,
            "task_id": self.task_id,
            "error": self.error,
            "age_seconds": round(time.time() - self.created_at, 1),
        }


class WorkerPool:
    """Idempotent registry of per-session worker microVMs."""

    def __init__(
        self,
        config: WorkerConfig,
        *,
        instavm_api_key: str | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._config = config
        self._api_key = instavm_api_key
        self._factory = client_factory or _default_client_factory
        self._workers: dict[str, WorkerInfo] = {}
        self._clients: dict[str, WorkerClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._guard:
            return self._locks.setdefault(session_id, asyncio.Lock())

    async def ensure_worker(self, session_id: str) -> WorkerInfo:
        """Spawn a worker for ``session_id`` if one is not already running."""
        lock = await self._lock_for(session_id)
        async with lock:
            existing = self._workers.get(session_id)
            if existing and existing.status in {"starting", "running"}:
                return existing
            info = WorkerInfo(session_id=session_id)
            self._workers[session_id] = info
            try:
                await self._spawn(session_id, info)
                info.status = "running"
            except Exception as exc:  # noqa: BLE001 - surface but don't crash the server
                info.status = "failed"
                info.error = str(exc)
                _log.exception("failed to spawn worker for session %s", session_id)
            return info

    async def _spawn(self, session_id: str, info: WorkerInfo) -> None:
        config = self._config
        env = {
            "ANTHROPIC_ENVIRONMENT_ID": config.environment_id,
            "ANTHROPIC_ENVIRONMENT_KEY": config.environment_key,
            "ANTHROPIC_SESSION_ID": session_id,
        }
        client = await asyncio.to_thread(
            self._factory,
            api_key=self._api_key,
            memory_mb=config.memory_mb,
            cpu_count=config.vcpu_count,
            env=env,
            metadata={"cma_session_id": session_id, "role": "cma-worker"},
        )
        self._clients[session_id] = client
        info.vm_id = _client_vm_id(client)

        await asyncio.to_thread(
            client.set_session_egress,
            allow_package_managers=True,
            allowed_domains=list(config.egress_domains),
        )
        result = await asyncio.to_thread(client.execute_async, build_worker_command(config))
        info.task_id = _task_id(result)

    async def stop(self, session_id: str) -> bool:
        client = self._clients.pop(session_id, None)
        info = self._workers.get(session_id)
        if info:
            info.status = "stopped"
        if client is None:
            return False
        try:
            await asyncio.to_thread(client.close_session)
        except Exception:  # noqa: BLE001
            _log.warning("failed to close worker session %s", session_id, exc_info=True)
        return True

    def list_workers(self) -> list[dict[str, Any]]:
        return [info.to_dict() for info in self._workers.values()]

    def count_active(self) -> int:
        return sum(1 for w in self._workers.values() if w.status in {"starting", "running"})


def _client_vm_id(client: Any) -> str | None:
    for attr in ("session_id", "vm_id", "id"):
        value = getattr(client, attr, None)
        if value:
            return str(value)
    getter = getattr(client, "get_session_info", None)
    if callable(getter):
        try:
            info = getter()
            if isinstance(info, dict):
                return str(info.get("session_id") or info.get("id") or "") or None
        except Exception:  # noqa: BLE001
            return None
    return None


def _task_id(result: Any) -> str | None:
    if isinstance(result, dict):
        return str(result.get("task_id") or result.get("id") or "") or None
    return getattr(result, "task_id", None)
