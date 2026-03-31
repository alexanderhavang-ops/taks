from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import logging
import sys

from mcp.server.fastmcp import FastMCP

from martine.config import load_config
from martine.state.paths import ensure_state_dirs
from martine.tools.taks_state import get_taks_state_summary
from martine.tools.docs_ref import list_reference_docs, search_reference_docs, get_reference_doc_context
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



@mcp.tool(name="list_reference_docs")
def list_reference_docs_tool(only_active: bool = True) -> dict:
    """List uploaded runtime reference documents available to Martine."""
    return list_reference_docs(only_active=only_active)


@mcp.tool(name="search_reference_docs")
def search_reference_docs_tool(query: str, limit: int = 8, doc_id: str = "") -> dict:
    """Search uploaded runtime reference documents by keyword over chunked extracted text."""
    return search_reference_docs(query=query, limit=limit, doc_id=doc_id)


@mcp.tool(name="get_reference_doc_context")
def get_reference_doc_context_tool(doc_id: str, chunk_id: str, window: int = 1) -> dict:
    """Return one matching chunk plus neighboring chunks for better document answer context."""
    return get_reference_doc_context(doc_id=doc_id, chunk_id=chunk_id, window=window)


@mcp.tool(name="get_current_time")
def get_current_time_tool() -> dict:
    """Return current UTC and local time."""
    return get_current_time()


@mcp.tool(name="get_my_position")
def get_my_position_tool(sender_uid: str = "", sender_callsign: str = "") -> dict:
    """Return latest known position for the sender."""
    return get_my_position(sender_uid=sender_uid, sender_callsign=sender_callsign)


@mcp.tool(name="get_my_mgrs")
def get_my_mgrs_tool(sender_uid: str = "", sender_callsign: str = "") -> dict:
    """Return latest known MGRS-like position string for the sender."""
    return get_my_mgrs(sender_uid=sender_uid, sender_callsign=sender_callsign)


@mcp.tool(name="get_contact_status")
def get_contact_status_tool(callsign_or_uid: str, sender_callsign: str = "") -> dict:
    """Return latest known status and position for a callsign or UID."""
    return get_contact_status(callsign_or_uid=callsign_or_uid, sender_callsign=sender_callsign)


@mcp.tool(name="get_last_seen")
def get_last_seen_tool(callsign_or_uid: str, sender_callsign: str = "") -> dict:
    """Return when a callsign or UID was last seen."""
    return get_last_seen(callsign_or_uid=callsign_or_uid, sender_callsign=sender_callsign)


@mcp.tool(name="get_distance_to_callsign")
def get_distance_to_callsign_tool(
    target_callsign_or_uid: str,
    sender_uid: str = "",
    sender_callsign: str = "",
) -> dict:
    """Return distance and bearing from the sender to a target callsign or UID."""
    return get_distance_to_callsign(
        target_callsign_or_uid=target_callsign_or_uid,
        sender_uid=sender_uid,
        sender_callsign=sender_callsign,
    )


@mcp.tool(name="get_nearest_friendly")
def get_nearest_friendly_tool(
    sender_uid: str = "",
    sender_callsign: str = "",
    limit: int = 20,
) -> dict:
    """Return the nearest friendly unit to the sender."""
    return get_nearest_friendly(
        sender_uid=sender_uid,
        sender_callsign=sender_callsign,
        limit=limit,
    )


@mcp.tool(name="get_enemy_contacts_near_me")
def get_enemy_contacts_near_me_tool(
    sender_uid: str = "",
    sender_callsign: str = "",
    radius_m: int = 2000,
    minutes: int = 60,
    limit: int = 20,
) -> dict:
    """Return hostile contacts recently seen near the sender."""
    return get_enemy_contacts_near_me(
        sender_uid=sender_uid,
        sender_callsign=sender_callsign,
        radius_m=radius_m,
        minutes=minutes,
        limit=limit,
    )


@mcp.tool(name="route_between_points")
def route_between_points_tool(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    profile: str = "foot",
) -> dict:
    """Return one OSRM route between two coordinates."""
    return route_between_points(
        from_lat=from_lat,
        from_lon=from_lon,
        to_lat=to_lat,
        to_lon=to_lon,
        profile=profile,
    )


@mcp.tool(name="route_alternatives_between_points")
def route_alternatives_between_points_tool(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    profile: str = "foot",
    max_alternatives: int = 3,
) -> dict:
    """Return OSRM route alternatives between two coordinates."""
    return route_alternatives_between_points(
        from_lat=from_lat,
        from_lon=from_lon,
        to_lat=to_lat,
        to_lon=to_lon,
        profile=profile,
        max_alternatives=max_alternatives,
    )


@mcp.tool(name="snap_point_to_network")
def snap_point_to_network_tool(
    lat: float,
    lon: float,
    profile: str = "foot",
    number: int = 1,
) -> dict:
    """Snap a coordinate to the nearest OSRM network point."""
    return snap_point_to_network(
        lat=lat,
        lon=lon,
        profile=profile,
        number=number,
    )


def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_streamable_http() -> None:
    mcp.run(transport="streamable-http")
