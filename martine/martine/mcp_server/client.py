from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _build_child_env() -> Dict[str, str]:
    env = dict(os.environ)

    wanted = [
        "/opt/tak/tools/takctl",
        "/opt/tak/tools/martine",
        "/opt/taks/takctl",
        "/opt/taks/martine",
    ]

    current = [p for p in str(env.get("PYTHONPATH") or "").split(":") if p]
    merged: List[str] = []
    seen = set()

    for p in wanted + current:
        s = str(p).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        merged.append(s)

    env["PYTHONPATH"] = ":".join(merged)
    return env


SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "martine.main", "mcp-stdio"],
    env=_build_child_env(),
)


async def _list_tools_async() -> List[Dict[str, Any]]:
    async with stdio_client(SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            out: List[Dict[str, Any]] = []
            for t in result.tools:
                out.append(
                    {
                        "name": getattr(t, "name", ""),
                        "description": getattr(t, "description", ""),
                        "input_schema": getattr(t, "inputSchema", None),
                    }
                )
            return out


async def _call_tool_async(name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    async with stdio_client(SERVER_PARAMS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments or {})
            content = getattr(result, "content", []) or []

            texts: List[str] = []
            structured: Any = None

            for item in content:
                text = getattr(item, "text", None)
                if text is not None:
                    texts.append(str(text))

            if len(texts) == 1:
                raw = texts[0]
                try:
                    structured = json.loads(raw)
                except Exception:
                    structured = None

            return {
                "ok": True,
                "tool_name": name,
                "arguments": arguments or {},
                "raw_text_parts": texts,
                "structured": structured,
                "is_error": bool(getattr(result, "isError", False)),
                "python_executable": sys.executable,
                "child_pythonpath": SERVER_PARAMS.env.get("PYTHONPATH", ""),
            }


def list_tools_via_mcp() -> List[Dict[str, Any]]:
    return asyncio.run(_list_tools_async())


def call_tool_via_mcp(name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return asyncio.run(_call_tool_async(name, arguments))
