from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from martine.config import load_config

from .voice_onboarding_common import (
    LOCAL_COT_TLS_HOST,
    LOCAL_COT_TLS_PORT,
    LOCAL_MARTI_HTTPS_PORT,
    _cfg_get,
    _first_nonempty,
    _host_token,
    _load_defaults,
    _load_murmur_password,
    _normalize_channels,
    _resolve_fqdn,
    _safe_slug,
    _state_root,
    _utc_now,
    _write_json,
    _write_text,
)
from .voice_onboarding_db import _wait_for_cot_router_event
from .voice_onboarding_delivery import (
    _build_fileshare_xml,
    _send_cot_tls,
    _upload_package_https,
    _wait_for_uploaded_content,
)
from .voice_onboarding_package import _render_voice_package


def send_voice_onboarding(
    target_callsign: str,
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    channels: Sequence[str] | str = (),
    channels_csv: str = "",
    mumble_port: int = 64738,
    mumble_tls: bool = True,
    force_tcp: bool = False,
    dry_run: bool = False,
    stale_hours: int = 2,
    **_: Any,
) -> dict[str, Any]:
    cfg = load_config()
    defaults = _load_defaults()

    target_callsign = str(target_callsign or "").strip()
    target_uid = str(target_uid or "").strip()
    if not target_callsign:
        return {
            "ok": False,
            "tool": "send_voice_onboarding",
            "error": "target_callsign is required",
        }

    sender_uid = _first_nonempty(_cfg_get(cfg, "chat_uid", ""), "ANDROID-MARTINE")
    sender_callsign = _first_nonempty(_cfg_get(cfg, "callsign", ""), "Martine")

    fqdn = _resolve_fqdn(cfg)
    content_host = fqdn
    node_name = _host_token(fqdn)
    mission_label = f"Samband-{node_name}"
    voice_port = int(mumble_port or 64738)
    server_password = _load_murmur_password(defaults)
    channel_names = _normalize_channels(
        channels=channels,
        channels_csv=channels_csv,
        defaults=defaults,
    )

    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    state_dir = _state_root(cfg) / "voice_onboarding" / f"{ts}-{_safe_slug(target_callsign)}"
    state_dir.mkdir(parents=True, exist_ok=True)

    xml_path = state_dir / "fileshare.xml"
    upload_resp_path = state_dir / f"{target_callsign}_{node_name}.upload.txt"
    result_path = state_dir / "result.json"

    try:
        rendered = _render_voice_package(
            target_callsign=target_callsign,
            target_uid=target_uid,
            sender_uid=sender_uid,
            sender_callsign=sender_callsign,
            node_name=node_name,
            mission_label=mission_label,
            fqdn=fqdn,
            voice_port=voice_port,
            channels=channel_names,
            server_password=server_password,
            state_dir=state_dir,
        )

        out: dict[str, Any] = {
            "ok": True,
            "tool": "send_voice_onboarding",
            "dry_run": bool(dry_run),
            "target_callsign": target_callsign,
            "target_uid": target_uid,
            "mission_name": rendered["manifest_name"],
            "channels": channel_names,
            "server": {
                "host": fqdn,
                "port": voice_port,
                "tls": bool(mumble_tls),
                "force_tcp": bool(force_tcp),
                "server_password_present": bool(server_password),
                "server_password": server_password,
            },
            "voice_setup": {
                "mission_label": mission_label,
                "auto_import_in_background": True,
                "atak_voice_path": "Settings -> TAK Voice",
                "select_mission_label": mission_label,
                "assign_controls": ["VS1", "VS2"],
                "available_channels": channel_names,
                "mumble_server_password_may_need_manual_entry": bool(server_password),
                "mumble_server_password": server_password,
                "user_guidance_sv": [
                    "Importen sker normalt automatiskt i bakgrunden; du behöver normalt inte öppna paketet manuellt.",
                    f"Gå till Settings -> TAK Voice och välj missionen {mission_label}.",
                    "Kontrollera att VS1 och VS2 är mappade till lämpliga kanaler från listan.",
                    "Om ATAK/Vx frågar efter Mumble-lösenord, skriv in serverlösenordet som visas här.",
                ],
            },
            "artifacts": {
                "state_dir": str(state_dir),
                "spec_path": rendered["spec_path"],
                "package_path": rendered["package_path"],
                "package_size_bytes": rendered["package_size_bytes"],
                "display_filename": rendered["display_filename"],
                "display_name": rendered["display_name"],
                "render_mode": rendered["render_mode"],
                "entries": rendered["entries"],
            },
        }

        if dry_run:
            _write_json(result_path, out)
            return out

        marti_hash = _upload_package_https(
            tak_host=fqdn,
            zip_path=Path(rendered["package_path"]),
            response_path=upload_resp_path,
        )
        content_ready = _wait_for_uploaded_content(
            tak_host=fqdn,
            marti_hash=marti_hash,
            timeout_seconds=5.0,
            interval_seconds=0.25,
        )
        sender_url = f"https://{content_host}:{LOCAL_MARTI_HTTPS_PORT}/Marti/sync/content?hash={marti_hash}"

        event_uid, xml_text = _build_fileshare_xml(
            dest_callsign=target_callsign,
            dest_uid=target_uid,
            sender_uid=sender_uid,
            sender_callsign=sender_callsign,
            display_name=rendered["display_name"],
            display_filename=rendered["display_filename"],
            sender_url=sender_url,
            package_size=int(rendered["package_size_bytes"]),
            package_hash=marti_hash,
            stale_hours=int(stale_hours or 2),
        )
        _write_text(xml_path, xml_text)

        _send_cot_tls(xml_text=xml_text, host=LOCAL_COT_TLS_HOST, port=LOCAL_COT_TLS_PORT)
        cot_router_event = _wait_for_cot_router_event(
            event_uid=event_uid,
            timeout_seconds=3.0,
            interval_seconds=0.25,
        )

        out["artifacts"]["fileshare_xml_path"] = str(xml_path)
        out["artifacts"]["upload_response_path"] = str(upload_resp_path)
        out["upload"] = {
            "tak_host": fqdn,
            "content_host": content_host,
            "marti_hash": marti_hash,
            "sender_url": sender_url,
            "content_ready": content_ready,
        }
        out["fileshare"] = {
            "event_uid": event_uid,
            "dest_callsign": target_callsign,
            "dest_uid": target_uid,
            "sender_uid": sender_uid,
            "sender_callsign": sender_callsign,
            "sent_to_host": LOCAL_COT_TLS_HOST,
            "sent_to_port": LOCAL_COT_TLS_PORT,
            "stale_hours": int(stale_hours or 2),
            "cot_router_event": cot_router_event,
        }

        out["delivery_status"] = "confirmed" if cot_router_event.get("ok") else "unconfirmed"
        if not cot_router_event.get("ok"):
            status = str(cot_router_event.get("status") or "").strip()
            if status == "probe_error":
                out["warning"] = (
                    "cot_router verification unavailable: "
                    + str(cot_router_event.get("error") or "unknown DB probe error")
                )
            else:
                out["warning"] = f"fileshare event {event_uid} was sent but not yet observed in cot_router"

        _write_json(result_path, out)
        return out

    except Exception as e:
        out = {
            "ok": False,
            "tool": "send_voice_onboarding",
            "dry_run": bool(dry_run),
            "target_callsign": target_callsign,
            "target_uid": target_uid,
            "channels": channel_names,
            "server": {
                "host": fqdn if "fqdn" in locals() else "",
                "port": int(mumble_port or 64738),
                "tls": bool(mumble_tls),
                "force_tcp": bool(force_tcp),
                "server_password_present": bool(server_password) if "server_password" in locals() else False,
            },
            "artifacts": {
                "state_dir": str(state_dir),
                "fileshare_xml_path": str(xml_path),
                "upload_response_path": str(upload_resp_path),
            },
            "error": f"{type(e).__name__}: {e}",
        }
        _write_json(result_path, out)
        return out
