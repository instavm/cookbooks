from __future__ import annotations

import os

DEFAULT_TASKS: tuple[str, ...] = ("fork-alpha", "fork-beta")
PARALLEL_CHILDREN = int(os.environ.get("FORK_CHILDREN", "2"))
