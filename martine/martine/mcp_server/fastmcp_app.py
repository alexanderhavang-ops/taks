from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import logging
import sys

from mcp.server.fastmcp import FastMCP

from martine.config import load_config
from martine.state.paths import ensure_state_dirs
from martine.tools.taks_state import get_taks_state_summary

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

mcp = FastMCP("Martine", json_response=True)


@mcp.tool()
def ping(message: str = "pong") -> dict:
    """Simple connectivity test."""
    return {
        "ok": True,
        "tool": "ping",
        "echo": message,
    }


@mcp.tool()
def get_taks_paths() -> dict:
    """Return key TAKS and Martine filesystem paths."""
    cfg = load_config()
    return {
        "ok": True,
        "tool": "get_taks_paths",
        "paths": {
            "taks_source": "/opt/taks",
            "martine_source": "/opt/taks/martine",
            "martine_state": cfg.state_dir,
            "tak_runtime": "/opt/tak",
        },
        "config": asdict(cfg),
        "exists": {
            "/opt/taks": Path("/opt/taks").exists(),
            "/opt/taks/martine": Path("/opt/taks/martine").exists(),
            "/opt/tak": Path("/opt/tak").exists(),
            cfg.state_dir: Path(cfg.state_dir).exists(),
        },
    }


@mcp.tool(name="ensure_martine_state_dirs")
def ensure_martine_state_dirs_tool() -> dict:
    """Create Martine runtime state directories if missing."""
    return {
        "ok": True,
        "tool": "ensure_martine_state_dirs",
        "dirs": ensure_state_dirs(),
    }


@mcp.tool(name="get_taks_state_summary")
def get_taks_state_summary_tool() -> dict:
    """Return a small summary of important TAKS runtime/source paths."""
    return {
        "ok": True,
        "tool": "get_taks_state_summary",
        "summary": get_taks_state_summary(),
    }


def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_streamable_http() -> None:
    mcp.run(transport="streamable-http")
