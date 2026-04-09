from __future__ import annotations

import uuid
import zipfile
import sqlite3
from pathlib import Path

MUMBLE_DB = Path("/var/lib/mumble-server/mumble-server.sqlite")
from typing import Any, Sequence
from xml.sax.saxutils import escape

from .voice_onboarding_common import _iso_z, _json_dump, _sha256_bytes, _utc_now, _write_json


def _pb_varint(n: int) -> bytes:
    x = int(n)
    if x < 0:
        raise ValueError(f"negative varint not supported: {x}")
    out = bytearray()
    while True:
        b = x & 0x7F
        x >>= 7
        if x:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _pb_key(field_no: int, wire_type: int) -> bytes:
    return _pb_varint((int(field_no) << 3) | int(wire_type))


def _pb_bytes(field_no: int, raw: bytes) -> bytes:
    payload = bytes(raw)
    return _pb_key(field_no, 2) + _pb_varint(len(payload)) + payload


def _pb_str(field_no: int, text: str) -> bytes:
    return _pb_bytes(field_no, str(text).encode("utf-8"))


def _pb_int(field_no: int, value: int) -> bytes:
    return _pb_key(field_no, 0) + _pb_varint(int(value))


def _pb_msg(field_no: int, payload: bytes) -> bytes:
    return _pb_bytes(field_no, payload)


def _build_vx_proto(
    *,
    mission_uuid: str,
    mission_name: str,
    channels: Sequence[dict[str, Any]],
    server_uuid: str,
    fqdn: str,
    port: int,
) -> bytes:
    channel_parts: list[bytes] = []

    for ch in channels:
        channel_uuid = str(ch.get("id") or uuid.uuid4()).strip()
        channel_name = str(ch.get("name") or "").strip()
        subtitle = str(ch.get("subtitle") or channel_name).strip()
        server_channel_id = int(ch.get("serverChannelId") or 1)

        channel_flags = _pb_int(1, 1) + _pb_str(2, subtitle)
        channel_msg = (
            _pb_str(1, channel_uuid)
            + _pb_str(2, channel_name)
            + _pb_int(3, server_channel_id)
            + _pb_str(4, server_uuid)
            + _pb_msg(6, channel_flags)
        )
        channel_parts.append(_pb_msg(3, _pb_msg(1, channel_msg)))

    server_msg = (
        _pb_str(1, server_uuid)
        + _pb_str(2, fqdn)
        + _pb_int(3, int(port))
        + _pb_bytes(5, b"")
        + _pb_str(7, "default")
    )

    return (
        _pb_str(1, mission_uuid)
        + _pb_str(2, mission_name)
        + b"".join(channel_parts)
        + _pb_msg(4, server_msg)
    )


def _build_manifest_xml(
    *,
    manifest_uid: str,
    manifest_name: str,
    json_entry: str,
    proto_entry: str,
    json_content_uid: str,
    proto_content_uid: str,
) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<MissionPackageManifest version="2">',
            '   <Configuration>',
            f'      <Parameter name="uid" value="{escape(manifest_uid)}"/>',
            f'      <Parameter name="name" value="{escape(manifest_name)}"/>',
            '      <Parameter name="onReceiveImport" value="true"/>',
            '      <Parameter name="onReceiveDelete" value="false"/>',
            '      <Parameter name="onReceiveAction" value="com.atakmap.android.gbr.multicastvoice.sharing.downloaded"/>',
            '   </Configuration>',
            '   <Contents>',
            f'      <Content ignore="false" zipEntry="{escape(json_entry)}">',
            f'         <Parameter name="uid" value="{escape(json_content_uid)}"/>',
            '      </Content>',
            f'      <Content ignore="false" zipEntry="{escape(proto_entry)}">',
            f'         <Parameter name="uid" value="{escape(proto_content_uid)}"/>',
            '      </Content>',
            '   </Contents>',
            '</MissionPackageManifest>',
        ]
    )



def _read_mumble_channel_ids() -> dict[str, int]:
    if not MUMBLE_DB.exists():
        return {}

    con = sqlite3.connect(str(MUMBLE_DB))
    try:
        cur = con.cursor()
        rows = cur.execute(
            "select channel_id, name from channels order by channel_id"
        ).fetchall()

        out: dict[str, int] = {}
        for channel_id, name in rows:
            ch_name = str(name or "").strip()
            if ch_name and ch_name not in out:
                out[ch_name] = int(channel_id)
        return out
    except Exception:
        return {}
    finally:
        con.close()


def _render_voice_package(
    *,
    target_callsign: str,
    target_uid: str,
    sender_uid: str,
    sender_callsign: str,
    node_name: str,
    mission_label: str,
    fqdn: str,
    voice_port: int,
    channels: Sequence[str],
    server_password: str,
    state_dir: Path,
) -> dict[str, Any]:
    manifest_uid = str(uuid.uuid4())
    mission_uuid = str(uuid.uuid4())
    server_uuid = str(uuid.uuid4())

    channel_specs: list[dict[str, Any]] = []
    channel_id_by_name = _read_mumble_channel_ids()
    fallback_next = 1

    for raw_name in channels:
        channel_name = str(raw_name or "").strip()
        if not channel_name:
            continue

        server_channel_id = int(channel_id_by_name.get(channel_name) or 0)
        if server_channel_id <= 0:
            server_channel_id = fallback_next
        fallback_next += 1

        channel_specs.append(
            {
                "id": str(uuid.uuid4()),
                "name": channel_name,
                "host": f"{fqdn}:{int(voice_port)}",
                "missionId": mission_uuid,
                "serverChannelId": server_channel_id,
                "subtitle": channel_name,
                "isMumble": True,
                "isEngineering": False,
                "port": -1,
            }
        )

    if not channel_specs:
        raise RuntimeError("at least one voice channel is required")

    json_dir = uuid.uuid4().hex
    proto_dir = uuid.uuid4().hex
    json_entry = f"{json_dir}/{mission_uuid}"
    proto_entry = f"{proto_dir}/{mission_uuid}_proto"

    manifest_name = f"{target_callsign}_{node_name}"
    display_name = f"{manifest_name} voice"
    display_filename = f"{manifest_name} voice.zip"

    voice_json = {
        "missionId": {"uuid": mission_uuid},
        "name": mission_label,
        "channels": channel_specs,
        "missionType": "COMBINED",
        "missionIP": "",
        "missionPort": "-1",
        "missionDefaultProtocol": "UDP",
    }

    proto_bytes = _build_vx_proto(
        mission_uuid=mission_uuid,
        mission_name=mission_label,
        channels=channel_specs,
        server_uuid=server_uuid,
        fqdn=fqdn,
        port=int(voice_port),
    )

    manifest_text = _build_manifest_xml(
        manifest_uid=manifest_uid,
        manifest_name=manifest_name,
        json_entry=json_entry,
        proto_entry=proto_entry,
        json_content_uid=str(uuid.uuid4()),
        proto_content_uid=str(uuid.uuid4()),
    )

    spec = {
        "schema": "taks.voice.vx_package.v1",
        "render_mode": "vx_mission_package_v1",
        "generated_at": _iso_z(_utc_now()),
        "node_name": node_name,
        "mission_label": mission_label,
        "fqdn": fqdn,
        "voice_port": int(voice_port),
        "manifest_uid": manifest_uid,
        "manifest_name": manifest_name,
        "mission_uuid": mission_uuid,
        "server_uuid": server_uuid,
        "target": {"callsign": target_callsign, "uid": target_uid},
        "sender": {"callsign": sender_callsign, "uid": sender_uid},
        "server_password_present": bool(server_password),
        "channels": list(channels),
        "json_entry": json_entry,
        "proto_entry": proto_entry,
        "voice_json": voice_json,
    }

    spec_path = state_dir / "voice_spec.json"
    zip_path = state_dir / display_filename
    json_text = _json_dump(voice_json)
    _write_json(spec_path, spec)

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST/manifest.xml", manifest_text.encode("utf-8"))
        zf.writestr(json_entry, json_text.encode("utf-8"))
        zf.writestr(proto_entry, proto_bytes)

    package_bytes = zip_path.read_bytes()
    return {
        "spec": spec,
        "spec_path": str(spec_path),
        "package_path": str(zip_path),
        "package_size_bytes": len(package_bytes),
        "package_sha256": _sha256_bytes(package_bytes),
        "display_name": display_name,
        "display_filename": display_filename,
        "render_mode": "vx_mission_package_v1",
        "entries": ["MANIFEST/manifest.xml", json_entry, proto_entry],
        "manifest_name": manifest_name,
        "mission_uuid": mission_uuid,
    }
