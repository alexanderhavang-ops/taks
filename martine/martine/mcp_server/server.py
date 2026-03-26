from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from martine.config import load_config
from martine.state.paths import ensure_state_dirs
from martine.tools.taks_state import get_taks_state_summary


def list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "ping",
            "description": "Simple connectivity test.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_taks_paths",
            "description": "Return key TAKS and Martine filesystem paths.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "ensure_martine_state_dirs",
            "description": "Create Martine runtime state directories if missing.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "get_taks_state_summary",
            "description": "Return a small summary of important TAKS runtime/source paths.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ]


def call_tool(name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = arguments or {}
    cfg = load_config()

    if name == "ping":
        return {
            "ok": True,
            "tool": "ping",
            "echo": str(args.get("message", "pong")),
        }

    if name == "get_taks_paths":
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

    if name == "ensure_martine_state_dirs":
        return {
            "ok": True,
            "tool": "ensure_martine_state_dirs",
            "dirs": ensure_state_dirs(),
        }

    if name == "get_taks_state_summary":
        return {
            "ok": True,
            "tool": "get_taks_state_summary",
            "summary": get_taks_state_summary(),
        }

    raise ValueError(f"unknown tool: {name}")
