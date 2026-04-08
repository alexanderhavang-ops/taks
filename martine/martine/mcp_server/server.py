from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from martine.config import load_config
from martine.state.paths import ensure_state_dirs
from martine.tools.taks_state import get_taks_state_summary
from martine.tools.docs_ref import list_reference_docs, search_reference_docs, search_reference_docs_semantic, get_reference_doc_context, list_reference_doc_sections, get_reference_section
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
from martine.tools.osrm_geo import (
    route_between_points,
    route_alternatives_between_points,
    snap_point_to_network,
)
from martine.tools.voice_onboarding import send_voice_onboarding


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
            "name": "list_reference_docs",
            "description": "List uploaded runtime reference documents available to Martine.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "only_active": {"type": "boolean"}
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "search_reference_docs",
            "description": "Search uploaded runtime reference documents by keyword over chunked extracted text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "doc_id": {"type": "string"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },

        {
            "name": "search_reference_docs_semantic",
            "description": "Search uploaded runtime reference documents semantically over vectorized chunk text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "doc_id": {"type": "string"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },

        {
            "name": "get_reference_doc_context",
            "description": "Return one matching chunk plus neighboring chunks for better document answer context.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "window": {"type": "integer"}
                },
                "required": ["doc_id", "chunk_id"],
                "additionalProperties": False,
            },
        },

        {
            "name": "list_reference_doc_sections",
            "description": "List parsed sections/chapters for one uploaded reference document.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["doc_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_reference_section",
            "description": "Fetch one parsed section by section_id or title_query from an uploaded reference document.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "section_id": {"type": "string"},
                    "title_query": {"type": "string"},
                    "max_chars": {"type": "integer"}
                },
                "required": ["doc_id"],
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
        {
            "name": "send_voice_onboarding",
            "description": "Create and send a semantic Vx/Mumble voice onboarding package to a TAK contact. If the user means themselves, use sender_callsign and sender_uid from RUN_CONTEXT.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_callsign": {"type": "string"},
                    "target_uid": {"type": "string"},
                    "sender_callsign": {"type": "string"},
                    "sender_uid": {"type": "string"},
                    "profile": {"type": "string"},
                    "mission_name": {"type": "string"},
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "mumble_host": {"type": "string"},
                    "mumble_port": {"type": "integer"},
                    "force_tcp": {"type": "boolean"},
                    "server_password": {"type": "string"},
                    "channel_passwords": {
                        "type": "object",
                        "additionalProperties": {"type": "string"}
                    },
                    "dry_run": {"type": "boolean"}
                },
                "required": [],
                "additionalProperties": false
            }
        },
        {
            "name": "route_between_points",
            "description": "Return one OSRM route between two coordinates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "from_lat": {"type": "number"},
                    "from_lon": {"type": "number"},
                    "to_lat": {"type": "number"},
                    "to_lon": {"type": "number"},
                    "profile": {"type": "string"},
                },
                "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
                "additionalProperties": False,
            },
        },
        {
            "name": "route_alternatives_between_points",
            "description": "Return OSRM route alternatives between two coordinates.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "from_lat": {"type": "number"},
                    "from_lon": {"type": "number"},
                    "to_lat": {"type": "number"},
                    "to_lon": {"type": "number"},
                    "profile": {"type": "string"},
                    "max_alternatives": {"type": "integer"},
                },
                "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
                "additionalProperties": False,
            },
        },
        {
            "name": "snap_point_to_network",
            "description": "Snap a coordinate to the nearest OSRM network point.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "profile": {"type": "string"},
                    "number": {"type": "integer"},
                },
                "required": ["lat", "lon"],
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


    if name == "list_reference_docs":
        return list_reference_docs(
            only_active=bool(args.get("only_active", True)),
        )

    if name == "search_reference_docs":
        return search_reference_docs(
            query=str(args.get("query", "")),
            limit=int(args.get("limit", 8) or 8),
            doc_id=str(args.get("doc_id", "")),
        )

    if name == "search_reference_docs_semantic":
        return search_reference_docs_semantic(
            query=str(args.get("query", "")),
            limit=int(args.get("limit", 8) or 8),
            doc_id=str(args.get("doc_id", "")),
        )


    if name == "get_reference_doc_context":
        return get_reference_doc_context(
            doc_id=str(args.get("doc_id", "")),
            chunk_id=str(args.get("chunk_id", "")),
            window=int(args.get("window", 1) or 1),
        )


    if name == "list_reference_doc_sections":
        return list_reference_doc_sections(
            doc_id=str(args.get("doc_id", "")),
            limit=int(args.get("limit", 200) or 200),
        )

    if name == "get_reference_section":
        return get_reference_section(
            doc_id=str(args.get("doc_id", "")),
            section_id=str(args.get("section_id", "")),
            title_query=str(args.get("title_query", "")),
            max_chars=int(args.get("max_chars", 6000) or 6000),
        )

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

    if name == "route_between_points":
        return route_between_points(
            from_lat=float(args.get("from_lat")),
            from_lon=float(args.get("from_lon")),
            to_lat=float(args.get("to_lat")),
            to_lon=float(args.get("to_lon")),
            profile=str(args.get("profile", "foot")),
        )

    if name == "route_alternatives_between_points":
        return route_alternatives_between_points(
            from_lat=float(args.get("from_lat")),
            from_lon=float(args.get("from_lon")),
            to_lat=float(args.get("to_lat")),
            to_lon=float(args.get("to_lon")),
            profile=str(args.get("profile", "foot")),
            max_alternatives=int(args.get("max_alternatives", 3)),
        )

    if name == "snap_point_to_network":
        return snap_point_to_network(
            lat=float(args.get("lat")),
            lon=float(args.get("lon")),
            profile=str(args.get("profile", "foot")),
            number=int(args.get("number", 1)),
        )

    raise ValueError(f"unknown tool: {name}")
