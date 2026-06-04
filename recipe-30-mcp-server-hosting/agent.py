"""MCP server hosting — no agent loop; stub for cookbook layout."""

from __future__ import annotations

from lib.config import MCP_SERVER_NAME


def server_name() -> str:
    return MCP_SERVER_NAME
