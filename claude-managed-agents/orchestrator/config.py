"""Runtime configuration for the orchestrator, read from the environment.

Values that vary per deployment are read lazily so tests can patch the
environment with ``monkeypatch`` before importing the worker pool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# The only webhook event the orchestrator consumes.
TRIGGER_EVENT = "session.status_run_started"

# Hosts a worker microVM must reach: Anthropic's control plane (work queue,
# results, skill download). Extend this list to give the agent access to
# additional third-party APIs — each of which should also be vault-injected.
DEFAULT_WORKER_EGRESS_DOMAINS = ("api.anthropic.com",)


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class WorkerConfig:
    """Settings for spawning a per-session worker microVM."""

    environment_id: str
    # Placeholder by default; the real environment key is injected at egress
    # from the org vault. Set ANTHROPIC_ENVIRONMENT_KEY to a real value only for
    # local/dev runs without vault injection.
    environment_key: str
    workdir: str
    max_idle: str
    ant_version: str
    memory_mb: int
    vcpu_count: int
    egress_domains: tuple[str, ...]


def load_worker_config() -> WorkerConfig:
    from lib.secrets import vault_credential

    extra = [d.strip() for d in (os.environ.get("WORKER_EGRESS_DOMAINS") or "").split(",") if d.strip()]
    domains = tuple(dict.fromkeys((*DEFAULT_WORKER_EGRESS_DOMAINS, *extra)))
    return WorkerConfig(
        environment_id=(os.environ.get("ANTHROPIC_ENVIRONMENT_ID") or "").strip(),
        environment_key=vault_credential("ANTHROPIC_ENVIRONMENT_KEY"),
        workdir=os.environ.get("WORKER_WORKDIR", "/workspace"),
        max_idle=os.environ.get("WORKER_MAX_IDLE", "30s"),
        ant_version=os.environ.get("ANT_VERSION", "1.12.0"),
        memory_mb=_int_env("WORKER_MEMORY_MB", 2048),
        vcpu_count=_int_env("WORKER_VCPU", 2),
        egress_domains=domains,
    )


def dispatcher_debounce_ms() -> int:
    return _int_env("DISPATCHER_DEBOUNCE_MS", 250)
