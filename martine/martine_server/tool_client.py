from __future__ import annotations

from typing import Any


def list_tools() -> list[dict[str, Any]]:
    from martine.mcp_server.client import list_tools_via_mcp
    return list_tools_via_mcp()


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    from martine.mcp_server.client import call_tool_via_mcp
    return call_tool_via_mcp(name, arguments or {})
