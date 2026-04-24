from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from martine.config import load_config

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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _path_has_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    for p in path.rglob("*"):
        if p.is_file():
            return True
    return False


def _default_maps_library_dir() -> Path:
    candidates = [
        Path("/opt/tak/tools/takctl/data/library/maps"),
        Path("/opt/taks/takctl/data/library/maps"),
    ]
    for p in candidates:
        if _path_has_files(p):
            return p
    existing = _first_existing(candidates)
    return existing if existing is not None else candidates[0]


def _stable_manifest_uid() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "taks:library-mission-package:maps"))


def _collect_map_files(library_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for src in sorted(library_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(library_dir)
        if any(str(part).startswith(".") for part in rel.parts):
            continue
        rel_s = rel.as_posix()
        if not rel_s:
            continue
        out.append(
            {
                "source_path": str(src),
                "relpath": rel_s,
                "zip_entry": f"maps/{rel_s}",
                "size_bytes": src.stat().st_size,
                "sha256": _sha256_file(src),
            }
        )
    return out


def _render_manifest_xml(*, manifest_uid: str, display_filename: str, files: list[dict[str, Any]]) -> str:
    lines = [
        '<MissionPackageManifest version="2">',
        "  <Configuration>",
        f'    <Parameter name="uid" value="{escape(manifest_uid)}"/>',
        f'    <Parameter name="name" value="{escape(display_filename)}"/>',
        '    <Parameter name="onReceiveImport" value="true"/>',
        '    <Parameter name="onReceiveDelete" value="false"/>',
        "  </Configuration>",
        "  <Contents>",
    ]
    for item in files:
        lines.append(
            f'    <Content ignore="false" zipEntry="{escape(str(item["zip_entry"]))}"/>'
        )
    lines.extend(
        [
            "  </Contents>",
            "</MissionPackageManifest>",
            "",
        ]
    )
    return "\n".join(lines)


def build_maps_package(*, requested_by: str, state_root: Path) -> dict[str, Any]:
    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(state_root) / f"{ts}-{_safe_slug(requested_by)}-maps-basic"
    run_dir.mkdir(parents=True, exist_ok=True)

    library_dir = _default_maps_library_dir()
    if not library_dir.exists():
        raise RuntimeError(f"maps library directory not found: {library_dir}")

    files = _collect_map_files(library_dir)
    if not files:
        raise RuntimeError(f"maps library is empty: {library_dir}")

    display_name = "ATAK maps basic"
    display_filename = "ATAK-maps-basic.zip"
    manifest_uid = _stable_manifest_uid()

    package_zip = run_dir / display_filename
    manifest_xml = _render_manifest_xml(
        manifest_uid=manifest_uid,
        display_filename=display_filename,
        files=files,
    )

    with zipfile.ZipFile(
        package_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        zf.writestr("MANIFEST/manifest.xml", manifest_xml)
        for item in files:
            zf.write(item["source_path"], arcname=item["zip_entry"])

    manifest_json = {
        "ok": True,
        "kind": "library_maps_mission_package",
        "package_id": "maps-basic",
        "title": display_name,
        "display_name": display_name,
        "display_filename": display_filename,
        "manifest_uid": manifest_uid,
        "library_root": str(library_dir),
        "requested_by": requested_by,
        "generated_at": _utc_now().isoformat(),
        "files": [
            {
                "relpath": str(item["relpath"]),
                "zip_entry": str(item["zip_entry"]),
                "size_bytes": int(item["size_bytes"]),
                "sha256": str(item["sha256"]),
            }
            for item in files
        ],
    }

    built = {
        **manifest_json,
        "run_dir": str(run_dir),
        "registry_path": "",
        "artifacts": {
            "package_zip": str(package_zip),
            "manifest_json": str(run_dir / "manifest.json"),
            "manifest_xml": str(run_dir / "manifest.xml"),
        },
    }

    _write_text(run_dir / "manifest.xml", manifest_xml)
    _write_json(run_dir / "manifest.json", manifest_json)
    _write_json(run_dir / "result.json", built)
    return built


def send_map_onboarding(
    target_callsign: str,
    target_uid: str = "",
    sender_callsign: str = "",
    sender_uid: str = "",
    dry_run: bool = False,
    stale_hours: int = 2,
    **_: Any,
) -> dict[str, Any]:
    cfg = load_config()

    target_callsign = str(target_callsign or "").strip()
    target_uid = str(target_uid or "").strip()

    if not target_callsign:
        return {
            "ok": False,
            "tool": "send_map_onboarding",
            "error": "target_callsign is required",
        }

    package_id = "maps-basic"
    sender_uid = _first_nonempty(sender_uid, _cfg_get(cfg, "chat_uid", ""), "ANDROID-MARTINE")
    sender_callsign = _first_nonempty(sender_callsign, _cfg_get(cfg, "callsign", ""), "Martine")
    fqdn = _resolve_fqdn(cfg)
    content_host = fqdn

    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    fallback_state_dir = _state_root(cfg) / "map_onboarding" / f"{ts}-{_safe_slug(target_callsign)}-{package_id}"
    fallback_state_dir.mkdir(parents=True, exist_ok=True)

    result_path = fallback_state_dir / "result.json"

    try:
        built = build_maps_package(
            requested_by=f"{sender_callsign}:{target_callsign}",
            state_root=_state_root(cfg) / "map_onboarding",
        )

        state_dir = Path(str(built["run_dir"]))
        xml_path = state_dir / "fileshare.xml"
        upload_resp_path = state_dir / f"{_safe_slug(target_callsign)}_{package_id}.upload.txt"
        zip_path = Path(str(built["artifacts"]["package_zip"]))

        display_name = str(built.get("display_name") or built.get("title") or package_id).strip() or package_id
        display_filename = str(built.get("display_filename") or zip_path.name).strip() or zip_path.name

        user_message_en = (
            "I'm sending you the onboarding maps for this server. "
            "Open the package in ATAK Data Packages and import it. "
            "This should be quick and painless."
        )

        user_message_sv = (
            "Jag skickar onboarding-kartorna för den här servern. "
            "Öppna paketet under Data Packages i ATAK och importera det. "
            "Det här ska gå snabbt och smidigt."
        )

        out: dict[str, Any] = {
            "ok": True,
            "tool": "send_map_onboarding",
            "dry_run": bool(dry_run),
            "target_callsign": target_callsign,
            "target_uid": target_uid,
            "package_id": package_id,
            "mission_name": display_name,
            "map_setup": {
                "requires_user_import_confirmation": True,
                "user_message_en": user_message_en,
                "user_message_sv": user_message_sv,
                "user_guidance_en": [
                    "Open the hamburger menu in ATAK.",
                    "Open Data Packages.",
                    f"Open the package {display_name}.",
                    "Import/apply the package.",
                    "Wait for the maps to appear in ATAK.",
                ],
                "user_guidance_sv": [
                    "Öppna hamburgermenyn i ATAK.",
                    "Öppna Data Packages.",
                    f"Öppna paketet {display_name}.",
                    "Importera/tillämpa paketet.",
                    "Vänta tills kartorna syns i ATAK.",
                ],
            },
            "artifacts": {
                "state_dir": str(state_dir),
                "package_path": str(zip_path),
                "package_size_bytes": int(zip_path.stat().st_size),
                "display_filename": display_filename,
                "display_name": display_name,
                "build_result_path": str(state_dir / "result.json"),
                "manifest_json_path": str(state_dir / "manifest.json"),
                "manifest_xml_path": str(state_dir / "manifest.xml"),
                "library_root": str(built.get("library_root") or ""),
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
            "tool": "send_map_onboarding",
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
