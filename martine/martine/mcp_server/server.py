from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from martine.config import load_config
from martine.state.paths import ensure_state_dirs
from martine.tools.taks_state import get_taks_state_summary
from martine.tools.cot_sa import (
    get_contact_status,
    get_current_time,
    get_distance_to_callsign,
    get_enemy_contacts_near_me,
    get_last_seen,
    get_my_mgrs,
    get_my_position,
    get_nearest_friendly,
)


def list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "ping",
            "description": "Simple connectivity test.",
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
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
        {
            "name": "get_current_time",
            "description": "Return current UTC and local time.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "get_my_position",
            "description": "Return latest known position for the sender.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sender_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_my_mgrs",
            "description": "Return latest known MGRS-like position string for the sender.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sender_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_contact_status",
            "description": "Return latest known status and position for a callsign or UID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "callsign_or_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                },
                "required": ["callsign_or_uid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_last_seen",
            "description": "Return when a callsign or UID was last seen.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "callsign_or_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                },
                "required": ["callsign_or_uid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_distance_to_callsign",
            "description": "Return distance and bearing from the sender to a target callsign or UID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_callsign_or_uid": {"type": "string"},
                    "sender_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                },
                "required": ["target_callsign_or_uid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_nearest_friendly",
            "description": "Return the nearest friendly unit to the sender.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sender_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_enemy_contacts_near_me",
            "description": "Return hostile contacts recently seen near the sender.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sender_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                    "radius_m": {"type": "integer"},
                    "minutes": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": [],
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

    if name == "get_current_time":
        return get_current_time()

    if name == "get_my_position":
        return get_my_position(
            sender_uid=str(args.get("sender_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
        )

    if name == "get_my_mgrs":
        return get_my_mgrs(
            sender_uid=str(args.get("sender_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
        )

    if name == "get_contact_status":
        return get_contact_status(
            callsign_or_uid=str(args.get("callsign_or_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
        )

    if name == "get_last_seen":
        return get_last_seen(
            callsign_or_uid=str(args.get("callsign_or_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
        )

    if name == "get_distance_to_callsign":
        return get_distance_to_callsign(
            target_callsign_or_uid=str(args.get("target_callsign_or_uid", "")),
            sender_uid=str(args.get("sender_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
        )

    if name == "get_nearest_friendly":
        return get_nearest_friendly(
            sender_uid=str(args.get("sender_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
            limit=int(args.get("limit", 20)),
        )

    if name == "get_enemy_contacts_near_me":
        return get_enemy_contacts_near_me(
            sender_uid=str(args.get("sender_uid", "")),
            sender_callsign=str(args.get("sender_callsign", "")),
            radius_m=int(args.get("radius_m", 2000)),
            minutes=int(args.get("minutes", 60)),
            limit=int(args.get("limit", 20)),
        )

    raise ValueError(f"unknown tool: {name}")
