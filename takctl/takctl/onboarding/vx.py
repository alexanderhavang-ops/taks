from __future__ import annotations

import json
import secrets
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _hex32() -> str:
    return secrets.token_hex(16)


def _uuid() -> str:
    return str(uuid.uuid4())


def _pb_varint(n: int) -> bytes:
    if n < 0:
        raise ValueError("protobuf varint must be non-negative")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _pb_key(field_no: int, wire_type: int) -> bytes:
    return _pb_varint((field_no << 3) | wire_type)


def _pb_len(b: bytes) -> bytes:
    return _pb_varint(len(b)) + b


def _pb_str(field_no: int, s: str) -> bytes:
    b = (s or "").encode("utf-8")
    return _pb_key(field_no, 2) + _pb_len(b)


def _pb_int(field_no: int, n: int) -> bytes:
    return _pb_key(field_no, 0) + _pb_varint(int(n))


def _pb_bytes(field_no: int, b: bytes) -> bytes:
    return _pb_key(field_no, 2) + _pb_len(b)


def _channel_inner(
    *,
    channel_id: str,
    channel_name: str,
    server_channel_id: int,
    server_id: str,
    subtitle: str,
) -> bytes:
    extra = b""
    extra += _pb_int(1, 1)
    extra += _pb_str(2, subtitle)

    out = b""
    out += _pb_str(1, channel_id)
    out += _pb_str(2, channel_name)
    out += _pb_int(3, int(server_channel_id))
    out += _pb_str(4, server_id)
    out += _pb_bytes(6, extra)
    return out


def _channel_wrapper(
    *,
    channel_id: str,
    channel_name: str,
    server_channel_id: int,
    server_id: str,
    subtitle: str,
) -> bytes:
    return _pb_bytes(
        1,
        _channel_inner(
            channel_id=channel_id,
            channel_name=channel_name,
            server_channel_id=server_channel_id,
            server_id=server_id,
            subtitle=subtitle,
        ),
    )


def _server_inner(*, server_id: str, host: str, port: int) -> bytes:
    out = b""
    out += _pb_str(1, server_id)
    out += _pb_str(2, host)
    out += _pb_int(3, int(port))
    out += _pb_str(5, "")
    out += _pb_str(7, "default")
    return out


def _server_wrapper(*, server_id: str, host: str, port: int) -> bytes:
    return _pb_bytes(1, _server_inner(server_id=server_id, host=host, port=port))


def _normalize_channel_specs(
    *,
    channels: list[dict[str, Any]] | None = None,
    channel_name: str = "",
    server_channel_id: int = 1,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    raw_items: list[dict[str, Any]] = []
    if channels:
        for item in channels:
            if isinstance(item, dict):
                raw_items.append(dict(item))
            else:
                raw_items.append({"name": str(item or "").strip()})
    elif str(channel_name or "").strip():
        raw_items.append(
            {
                "name": str(channel_name).strip(),
                "subtitle": str(channel_name).strip(),
                "server_channel_id": int(server_channel_id),
            }
        )

    next_id = 1
    for item in raw_items:
        name = str(
            item.get("name")
            or item.get("channel_name")
            or item.get("channel")
            or ""
        ).strip()
        if not name or name in seen:
            continue
        seen.add(name)

        subtitle = str(item.get("subtitle") or name).strip() or name

        sid_raw = item.get("server_channel_id")
        if sid_raw in (None, "", 0):
            sid = next_id
        else:
            try:
                sid = int(sid_raw)
            except Exception:
                sid = next_id

        out.append(
            {
                "name": name,
                "subtitle": subtitle,
                "server_channel_id": sid,
            }
        )
        next_id += 1

    if not out:
        raise RuntimeError("VX package requires at least one channel")

    return out


def _vx_proto(
    *,
    mission_id: str,
    mission_name: str,
    channels: list[dict[str, Any]],
    server_id: str,
    host: str,
    port: int,
) -> bytes:
    out = b""
    out += _pb_str(1, mission_id)
    out += _pb_str(2, mission_name)

    for ch in channels:
        out += _pb_bytes(
            3,
            _channel_wrapper(
                channel_id=str(ch["id"]),
                channel_name=str(ch["name"]),
                server_channel_id=int(ch["server_channel_id"]),
                server_id=server_id,
                subtitle=str(ch["subtitle"]),
            ),
        )

    out += _pb_bytes(
        4,
        _server_wrapper(
            server_id=server_id,
            host=host,
            port=port,
        ),
    )
    return out


def _vx_json(
    *,
    mission_id: str,
    mission_name: str,
    channels: list[dict[str, Any]],
    host: str,
    port: int,
) -> bytes:
    obj = {
        "missionId": {"uuid": mission_id},
        "name": mission_name,
        "channels": [
            {
                "id": str(ch["id"]),
                "name": str(ch["name"]),
                "host": f"{host}:{int(port)}",
                "missionId": mission_id,
                "serverChannelId": int(ch["server_channel_id"]),
                "subtitle": str(ch["subtitle"]),
                "isMumble": True,
                "isEngineering": False,
                "port": -1,
            }
            for ch in channels
        ],
        "missionType": "COMBINED",
        "missionIP": "",
        "missionPort": "-1",
        "missionDefaultProtocol": "UDP",
    }
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _manifest_xml(*, package_name: str, json_entry: str, proto_entry: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<MissionPackageManifest version="2">
   <Configuration>
      <Parameter name="uid" value="{_uuid()}"/>
      <Parameter name="name" value="{package_name}"/>
      <Parameter name="onReceiveImport" value="true"/>
      <Parameter name="onReceiveDelete" value="false"/>
      <Parameter name="onReceiveAction" value="com.atakmap.android.gbr.multicastvoice.sharing.downloaded"/>
   </Configuration>
   <Contents>
      <Content ignore="false" zipEntry="{json_entry}">
         <Parameter name="uid" value="{_uuid()}"/>
      </Content>
      <Content ignore="false" zipEntry="{proto_entry}">
         <Parameter name="uid" value="{_uuid()}"/>
      </Content>
   </Contents>
</MissionPackageManifest>
"""


def _derive_topology(ctx: dict[str, Any]) -> dict[str, Any] | None:
    try:
        from takctl.onboarding.voice_topology import derive_voice_topology
        topo = derive_voice_topology(None, ctx)
        return topo if isinstance(topo, dict) else None
    except Exception:
        return None


def derive_vx_params(*, username: str, groups: list[str], selection: dict | None, base: str) -> dict:
    sel = selection or {}
    ctx = (sel.get("ctx") or {}) if isinstance(sel, dict) else {}

    callsign = str(ctx.get("callsign") or username or "user").strip()

    host = ""
    try:
        host = (urlparse(str(base)).hostname or "").strip()
    except Exception:
        host = ""
    if not host:
        host = str((sel.get("endpoints") or {}).get("stream_host") or "").strip()
    if not host:
        host = "127.0.0.1"

    topo = _derive_topology(ctx)

    package_stem = ""
    if groups:
        package_stem = str(groups[0] or "").strip()
    if not package_stem:
        package_stem = str(ctx.get("unit") or ctx.get("battalion") or username or "taks").strip()

    if topo:
        mission_name = str(topo.get("mission_label") or package_stem or "Samband").strip()
        channel_names = [str(x).strip() for x in (topo.get("seed_channels") or []) if str(x or "").strip()]
    else:
        mission_name = str(package_stem or "taks").strip()
        fallback = str(ctx.get("battalion_fal") or "VQ").strip() or "VQ"
        channel_names = [fallback]

    if not channel_names:
        channel_names = [str(ctx.get("battalion_fal") or "VQ").strip() or "VQ"]

    channel_specs = [
        {
            "name": name,
            "subtitle": name,
            "server_channel_id": idx,
        }
        for idx, name in enumerate(channel_names, start=1)
    ]

    package_name = f"{callsign}_{package_stem}"

    return {
        "package_name": package_name,
        "mission_name": mission_name,
        "channels": channel_specs,
        "channel_name": channel_specs[0]["name"],
        "host": host,
        "port": 64738,
        "server_channel_id": channel_specs[0]["server_channel_id"],
    }


def write_vx_mission_zip(
    out: str | Path,
    *,
    package_name: str,
    mission_name: str,
    host: str,
    port: int = 64738,
    channels: list[dict[str, Any]] | None = None,
    channel_name: str = "",
    server_channel_id: int = 1,
) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    raw_channels = _normalize_channel_specs(
        channels=channels,
        channel_name=channel_name,
        server_channel_id=server_channel_id,
    )

    mission_id = _uuid()
    server_id = _uuid()

    channel_payloads: list[dict[str, Any]] = []
    for ch in raw_channels:
        channel_payloads.append(
            {
                "id": _uuid(),
                "name": str(ch["name"]),
                "subtitle": str(ch["subtitle"]),
                "server_channel_id": int(ch["server_channel_id"]),
            }
        )

    json_dir = _hex32()
    proto_dir = _hex32()

    json_entry = f"{json_dir}/{mission_id}"
    proto_entry = f"{proto_dir}/{mission_id}_proto"

    manifest = _manifest_xml(
        package_name=package_name,
        json_entry=json_entry,
        proto_entry=proto_entry,
    )

    payload_json = _vx_json(
        mission_id=mission_id,
        mission_name=mission_name,
        channels=channel_payloads,
        host=host,
        port=port,
    )

    payload_proto = _vx_proto(
        mission_id=mission_id,
        mission_name=mission_name,
        channels=channel_payloads,
        server_id=server_id,
        host=host,
        port=port,
    )

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST/manifest.xml", manifest)
        zf.writestr(json_entry, payload_json)
        zf.writestr(proto_entry, payload_proto)
