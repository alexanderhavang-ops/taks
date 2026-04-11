from __future__ import annotations

from pathlib import Path
from typing import Any

from martine.config import load_config

from .plugin_onboarding_common import build_plugin_package
from .voice_onboarding_common import (
    LOCAL_COT_TLS_HOST,
    LOCAL_COT_TLS_PORT,
    LOCAL_MARTI_HTTPS_PORT,
    _cfg_get,
    _first_nonempty,
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


def send_plugin_onboarding(
    target_callsign: str,
    package_id: str,
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    registry_path: str = "",
    dry_run: bool = False,
    stale_hours: int = 2,
    **_: Any,
) -> dict[str, Any]:
    cfg = load_config()

    target_callsign = str(target_callsign or "").strip()
    target_uid = str(target_uid or "").strip()
    package_id = str(package_id or "").strip()
    registry_path = str(registry_path or "").strip()

    if not target_callsign:
        return {
            "ok": False,
            "tool": "send_plugin_onboarding",
            "error": "target_callsign is required",
        }

    if not package_id:
        return {
            "ok": False,
            "tool": "send_plugin_onboarding",
            "target_callsign": target_callsign,
            "error": "package_id is required",
        }

    sender_uid = _first_nonempty(sender_uid, _cfg_get(cfg, "chat_uid", ""), "ANDROID-MARTINE")
    sender_callsign = _first_nonempty(sender_callsign, _cfg_get(cfg, "callsign", ""), "Martine")
    fqdn = _resolve_fqdn(cfg)
    content_host = fqdn

    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    fallback_state_dir = _state_root(cfg) / "plugin_onboarding" / f"{ts}-{_safe_slug(target_callsign)}-{_safe_slug(package_id)}"
    fallback_state_dir.mkdir(parents=True, exist_ok=True)

    result_path = fallback_state_dir / "result.json"

    try:
        built = build_plugin_package(
            package_id=package_id,
            requested_by=f"{sender_callsign}:{target_callsign}",
            registry_path=Path(registry_path) if registry_path else None,
            state_root=_state_root(cfg) / "plugin_onboarding",
        )

        state_dir = Path(str(built["run_dir"]))
        xml_path = state_dir / "fileshare.xml"
        upload_resp_path = state_dir / f"{_safe_slug(target_callsign)}_{_safe_slug(package_id)}.upload.txt"
        zip_path = Path(str(built["artifacts"]["package_zip"]))

        display_name = str(built.get("title") or package_id).strip() or package_id
        display_filename = f"{package_id}.zip"

        out: dict[str, Any] = {
            "ok": True,
            "tool": "send_plugin_onboarding",
            "dry_run": bool(dry_run),
            "target_callsign": target_callsign,
            "target_uid": target_uid,
            "package_id": package_id,
            "mission_name": display_name,
            "plugin_setup": {
                "requires_user_install_confirmation": True,
                "user_guidance_sv": [
                    "ATAK ska hämta paketet via fileshare-länken.",
                    "Om Android frågar om installation av plugin/APK behöver användaren normalt godkänna installationen.",
                    "Om ATAK inte importerar automatiskt, öppna mottaget paket manuellt i ATAK.",
                ],
            },
            "artifacts": {
                "state_dir": str(state_dir),
                "package_path": str(zip_path),
                "package_size_bytes": int(zip_path.stat().st_size),
                "display_filename": display_filename,
                "display_name": display_name,
                "registry_path": registry_path or str(built.get("registry_path") or ""),
                "build_result_path": str(state_dir / "result.json"),
                "manifest_path": str(state_dir / "manifest.json"),
            },
            "package_build": built,
        }

        if dry_run:
            _write_json(state_dir / "delivery_result.json", out)
            return out

        marti_hash = _upload_package_https(
            tak_host=fqdn,
            zip_path=zip_path,
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
            display_name=display_name,
            display_filename=display_filename,
            sender_url=sender_url,
            package_size=int(zip_path.stat().st_size),
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

        _write_json(state_dir / "delivery_result.json", out)
        return out

    except Exception as e:
        out = {
            "ok": False,
            "tool": "send_plugin_onboarding",
            "dry_run": bool(dry_run),
            "target_callsign": target_callsign,
            "target_uid": target_uid,
            "package_id": package_id,
            "artifacts": {
                "state_dir": str(fallback_state_dir),
                "result_path": str(result_path),
            },
            "error": f"{type(e).__name__}: {e}",
        }
        _write_json(result_path, out)
        return out
