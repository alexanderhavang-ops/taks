from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import logging
import sys

from mcp.server.fastmcp import FastMCP

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
from martine.tools.map_onboarding import send_map_onboarding
from martine.tools.plugin_onboarding import send_plugin_onboarding
from martine.tools.voice_onboarding import send_voice_onboarding

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from martine.security import scoped_tool, current_principal


class ScopedFastMCP(FastMCP):
    def tool(self, *args, **kwargs):
        register = super().tool(*args, **kwargs)
        def decorate(function):
            return register(scoped_tool(function, kwargs.get('name') or function.__name__))
        return decorate


mcp = ScopedFastMCP("Martine", json_response=True)


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


@mcp.tool(name="search_reference_docs_semantic")
def search_reference_docs_semantic_tool(query: str, limit: int = 8, doc_id: str = "") -> dict:
    """Search uploaded runtime reference documents semantically over vectorized chunk text."""
    return search_reference_docs_semantic(query=query, limit=limit, doc_id=doc_id)


@mcp.tool(name="get_reference_doc_context")
def get_reference_doc_context_tool(doc_id: str, chunk_id: str, window: int = 1) -> dict:
    """Return one matching chunk plus neighboring chunks for better document answer context."""
    return get_reference_doc_context(doc_id=doc_id, chunk_id=chunk_id, window=window)


@mcp.tool(name="list_reference_doc_sections")
def list_reference_doc_sections_tool(doc_id: str, limit: int = 200) -> dict:
    """List parsed sections/chapters for one uploaded reference document."""
    return list_reference_doc_sections(doc_id=doc_id, limit=limit)


@mcp.tool(name="get_reference_section")
def get_reference_section_tool(doc_id: str, section_id: str = "", title_query: str = "", max_chars: int = 6000) -> dict:
    """Fetch one parsed section by section_id or title_query from an uploaded reference document."""
    return get_reference_section(doc_id=doc_id, section_id=section_id, title_query=title_query, max_chars=max_chars)


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


@mcp.tool(name="send_voice_onboarding")
def send_voice_onboarding_tool(
    target_callsign: str = "",
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    profile: str = "default",
    mission_name: str = "",
    channels: list[str] | None = None,
    mumble_host: str = "",
    mumble_port: int = 64738,
    force_tcp: bool = False,
    server_password: str = "",
    channel_passwords: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Create and send a semantic Vx/Mumble voice onboarding package to a TAK contact.
    Use this when the user asks to be onboarded for voice or asks Martine to send a voice package.
    If the user means themselves, pass sender_callsign/sender_uid from RUN_CONTEXT.
    """
    return send_voice_onboarding(
        target_callsign=target_callsign,
        target_uid=target_uid,
        sender_callsign=sender_callsign,
        sender_uid=sender_uid,
        profile=profile,
        mission_name=mission_name,
        channels=channels,
        mumble_host=mumble_host,
        mumble_port=mumble_port,
        force_tcp=force_tcp,
        server_password=server_password,
        channel_passwords=channel_passwords,
        dry_run=dry_run,
    )


@mcp.tool(name="send_plugin_onboarding")
def send_plugin_onboarding_tool(
    target_callsign: str = "",
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    package_id: str = "plugins-basic",
    registry_path: str = "",
    dry_run: bool = False,
) -> dict:
    """Create and send an ATAK plugin package to a TAK contact.
    Use this when the user asks Martine to send or install ATAK plugins.
    If the user means themselves, pass sender_callsign/sender_uid from RUN_CONTEXT.
    """
    return send_plugin_onboarding(
        target_callsign=target_callsign,
        target_uid=target_uid,
        sender_callsign=sender_callsign,
        sender_uid=sender_uid,
        package_id=package_id,
        registry_path=registry_path,
        dry_run=dry_run,
    )


@mcp.tool(name="send_map_onboarding")
def send_map_onboarding_tool(
    target_callsign: str = "",
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    dry_run: bool = False,
) -> dict:
    """Create and send an ATAK maps package to a TAK contact.
    Use this when the user asks Martine to send or install ATAK maps.
    If the user means themselves, pass sender_callsign/sender_uid from RUN_CONTEXT.
    """
    return send_map_onboarding(
        target_callsign=target_callsign,
        target_uid=target_uid,
        sender_callsign=sender_callsign,
        sender_uid=sender_uid,
        dry_run=dry_run,
    )


@mcp.tool(name="martine_offline_self_test")
def martine_offline_self_test() -> dict:
    """Run fixed Martine regression suites locally, without API inference calls.

    This is a bounded diagnostic, not arbitrary command execution.
    """
    import os
    import subprocess

    tests_dir = Path("/opt/tak/tools/martine/tests")
    if not tests_dir.is_dir():
        return {"ok": False, "error": "Martine node tests are not installed"}
    env = dict(os.environ)
    env["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    env.pop("OPENAI_API_KEY", None)
    cmd = [
        sys.executable, "-m", "unittest", "-v",
        "test_agents_migration",
        "test_agents_sdk_workflows",
        "test_martine_use_cases",
    ]
    try:
        proc = subprocess.run(
            cmd, env=env, text=True, capture_output=True,
            timeout=120, check=False,
            cwd=str(tests_dir),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Martine regression timeout after 120 seconds"}
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "summary": (proc.stdout + "\n" + proc.stderr)[-10000:],
    }


@mcp.tool(name="martine_live_inference_test")
def martine_live_inference_test(confirm_paid_api_calls: bool = False) -> dict:
    """Run two real OpenAI inference tests on this node.

    Requires explicit consent; makes paid API calls. Does not send GeoChat.
    """
    import os
    import subprocess
    if not confirm_paid_api_calls:
        return {"ok": False, "error": "confirm_paid_api_calls must be true"}
    tests = Path("/opt/tak/tools/martine/tests")
    if not tests.is_dir():
        return {"ok": False, "error": "Live test module not installed"}
    env = dict(os.environ)
    env["MARTINE_LIVE_TESTS"] = "1"
    env["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    cmd = [sys.executable, "-m", "unittest", "-v", "test_live_inference"]
    try:
        proc = subprocess.run(
            cmd, cwd=str(tests), env=env, capture_output=True,
            text=True, timeout=240, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Live inference tests timed out after 240 seconds"}
    # Report test case status only; do not return model outputs or secrets.
    lines = [
        line.strip()[:250] for line in proc.stderr.splitlines()
        if line.strip().startswith("test_real_") or line.strip().startswith("Ran ")
        or line.strip() in ("OK", "FAILED", "FAILED (failures=1)", "FAILED (errors=1)")
    ]
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "test_status": lines[-10:], "error": "See node-local test log" if proc.returncode else ""}


@mcp.tool()
def get_onboarding_diagnostics(username: str = "") -> dict:
    """Inspect this account's callsign, enrollment and attributed devices."""
    from takctl.services.business_diagnostics import onboarding
    return onboarding(current_principal().as_dict(), username)


@mcp.tool()
def get_my_connection_events(username: str = "") -> dict:
    """Own attributed CoT connection events; no global raw logs."""
    from takctl.services.business_diagnostics import own_events
    return own_events(current_principal().as_dict(), username)


@mcp.tool()
def business_read(service: str, operation: str, arguments: dict | None = None) -> dict:
    """Administrator: read native LDAP, Mumble or Openfire operational APIs."""
    from takctl.services.business_services import call
    return call(service, operation, arguments or {})


@mcp.tool()
def read_diagnostic_log(source: str, lines: int = 40) -> dict:
    """Administrator: bounded redacted logs. Sources voice_auth/openfire/takctl/installer/business_tests/nginx."""
    from takctl.services.business_diagnostics import log_tail
    return log_tail(current_principal().as_dict(), source, lines)


@mcp.tool()
def diagnostic_file_stat(source: str) -> dict:
    """Administrator: metadata for an allowlisted diagnostic log; no arbitrary paths."""
    from takctl.services.business_diagnostics import file_metadata
    return file_metadata(current_principal().as_dict(), source)


@mcp.tool()
def marti_read(resource: str) -> dict:
    """Administrator: Marti inputs or subscriptions, using managed LDAP administrator OAuth."""
    from takctl.services.marti_api import marti_json
    paths = {'inputs':'/Marti/api/inputs','subscriptions':'/Marti/api/subscriptions/all'}
    if resource not in paths:
        raise ValueError('Unknown read-only Marti resource')
    return {'ok':True, 'data':marti_json(paths[resource])}


@mcp.tool()
def request_business_change(service: str, operation: str, arguments: dict) -> dict:
    """Administrator: propose a native business change. A human must approve the returned action ID in the UI."""
    from takctl.services.martine_chat import propose_change
    return propose_change(current_principal().as_dict(), service, operation, arguments)


@mcp.tool()
def product_health() -> dict:
    """Administrator: TAK, enrollment, LDAP, Postgres, XMPP and voice listener status."""
    from takctl.services.business_diagnostics import product_health as health
    return health(current_principal().as_dict())


def run_stdio() -> None:
    mcp.run(transport="stdio")


def run_streamable_http() -> None:
    mcp.run(transport="streamable-http")

logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)

logging.getLogger("onnxruntime").setLevel(logging.ERROR)
