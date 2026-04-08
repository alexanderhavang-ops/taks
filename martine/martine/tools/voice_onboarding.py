from __future__ import annotations

import hashlib
import http.client
import json
import logging
import re
import socket
import ssl
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote
from xml.sax.saxutils import escape

from martine.config import load_config
from takctl.config import load_secrets


IDENTITY_DIR = Path("/opt/tak/tools/martine/runtime/identity")
CERT_PEM = IDENTITY_DIR / "client.pem"
KEY_PEM = IDENTITY_DIR / "client.key"
CA_PEM = IDENTITY_DIR / "ca.pem"

TAKS_ENV = Path("/opt/tak/etc/taks.env")
FQDN_FILES = [
    TAKS_ENV,
    Path("/opt/tak/FQDN"),
    Path("/opt/tak/bootstrap/fqdn"),
    Path("/opt/tak/bootstrap/fqdn.txt"),
]

MURMUR_SECRET_FILES = [
    Path("/opt/tak/bootstrap/secrets.d/murmur.conf"),
    Path("/opt/tak/tools/takctl/secrets.d/murmur.conf"),
]

DEFAULTS_CANDIDATES = [
    Path("/opt/tak/tools/martine/conf.d/voice_onboarding.json"),
    Path("/opt/taks/martine/confmeta/voice_onboarding.default.json"),
]

LOCAL_MARTI_HTTPS_PORT = 8443
LOCAL_COT_TLS_HOST = "127.0.0.1"
LOCAL_COT_TLS_PORT = 8089

DEFAULT_LAT = "55.597371"
DEFAULT_LON = "12.96644"
DEFAULT_HAE = "41.5758371100"
DEFAULT_CE = "12.04932404"
DEFAULT_LE = "NaN"

HASH_RE = re.compile(r"\bhash=([0-9a-fA-F]{32,128})\b")
SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

_LOG = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    _write_text(path, _json_dump(obj))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        txt = path.read_text(encoding="utf-8").strip()
        if not txt:
            return {}
        raw = json.loads(txt)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _merge_dict(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    out = dict(dst)
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _load_defaults() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for p in DEFAULTS_CANDIDATES:
        merged = _merge_dict(merged, _read_json(p))
    return merged


def _cfg_get(cfg: Any, name: str, default: Any = "") -> Any:
    return getattr(cfg, name, default)


def _first_nonempty(*vals: Any) -> str:
    for v in vals:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _safe_slug(text: Any) -> str:
    s = str(text or "").strip()
    if not s:
        return "item"
    s = SAFE_RE.sub("-", s).strip("-")
    return s.lower() or "item"


def _host_token(host: str) -> str:
    h = str(host or "").strip()
    if not h:
        return "server"
    return _safe_slug(h.split(".")[0])


def _state_root(cfg: Any) -> Path:
    return Path(str(_cfg_get(cfg, "state_dir", "/opt/tak/tools/martine/state")))


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
    except Exception:
        return {}
    return out


def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
    except Exception:
        return {}
    return out


def _resolve_fqdn(cfg: Any) -> str:
    env = _parse_env_file(TAKS_ENV)
    for key in ("TAKS_FQDN", "TAKS_NODE_FQDN"):
        val = str(env.get(key) or "").strip()
        if val:
            return val

    for path in FQDN_FILES[1:]:
        try:
            if not path.exists():
                continue
            txt = path.read_text(encoding="utf-8").strip()
            if txt:
                return txt.splitlines()[0].strip()
        except Exception:
            pass

    for cand in (
        _cfg_get(cfg, "fqdn", ""),
        _cfg_get(cfg, "tak_public_host", ""),
        _cfg_get(cfg, "public_host", ""),
    ):
        s = str(cand or "").strip()
        if s:
            return s

    try:
        fqdn = socket.getfqdn().strip()
        if fqdn:
            return fqdn
    except Exception:
        pass

    raise RuntimeError("could not resolve node FQDN")


def _resolve_ipv4(host: str) -> str:
    try:
        infos = socket.getaddrinfo(str(host), None, socket.AF_INET, socket.SOCK_STREAM)
        for info in infos:
            sockaddr = info[4]
            if sockaddr and sockaddr[0]:
                return str(sockaddr[0])
    except Exception:
        pass
    return str(host or "").strip()


def _load_murmur_password(defaults: dict[str, Any]) -> str:
    for path in MURMUR_SECRET_FILES:
        kv = _read_simple_kv(path)
        for key in ("serverpassword", "mumble_server_password", "server_password"):
            val = str(kv.get(key) or "").strip()
            if val:
                return val

    server = defaults.get("server") if isinstance(defaults.get("server"), dict) else {}
    for cand in (
        server.get("password") if isinstance(server, dict) else "",
        defaults.get("mumble_server_password"),
        defaults.get("server_password"),
    ):
        s = str(cand or "").strip()
        if s:
            return s
    return ""


def _normalize_channels(
    channels: Any = None,
    channels_csv: str = "",
    defaults: dict[str, Any] | None = None,
) -> list[str]:
    out: list[str] = []

    def add(v: Any) -> None:
        s = str(v or "").strip()
        if s and s not in out:
            out.append(s)

    if isinstance(channels, str):
        for part in channels.split(","):
            add(part)
    elif isinstance(channels, Iterable):
        for item in channels:
            if isinstance(item, dict):
                add(item.get("name") or item.get("path") or item.get("channel"))
            else:
                add(item)

    if channels_csv:
        for part in str(channels_csv).split(","):
            add(part)

    if not out and isinstance(defaults, dict):
        for key in ("channels", "default_channels"):
            raw = defaults.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        add(item.get("name") or item.get("path") or item.get("channel"))
                    else:
                        add(item)

    if not out:
        out = ["Ledning"]

    return out


def _pem_key_password() -> str | None:
    sec = load_secrets()
    for key in (
        "martine_client_p12_pass",
        "user_key_pass",
        "onboarding_client_p12_default_pass",
        "cert_pass",
    ):
        val = str(sec.get(key, "") or "").strip()
        if val:
            return val
    return None


def _mtls_context() -> ssl.SSLContext:
    for p in (CERT_PEM, KEY_PEM, CA_PEM):
        if not p.exists():
            raise RuntimeError(f"missing Martine identity file: {p}")

    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(CA_PEM))
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_cert_chain(
        certfile=str(CERT_PEM),
        keyfile=str(KEY_PEM),
        password=_pem_key_password(),
    )
    return ctx


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    channel_uuid: str,
    channel_name: str,
    server_uuid: str,
    fqdn: str,
    port: int,
    subtitle: str,
) -> bytes:
    channel_flags = (
        _pb_int(1, 1) +
        _pb_str(2, subtitle)
    )

    channel_msg = (
        _pb_str(1, channel_uuid) +
        _pb_str(2, channel_name) +
        _pb_int(3, 1) +
        _pb_str(4, server_uuid) +
        _pb_msg(6, channel_flags)
    )

    channel_container = _pb_msg(1, channel_msg)

    server_msg = (
        _pb_str(1, server_uuid) +
        _pb_str(2, fqdn) +
        _pb_int(3, int(port)) +
        _pb_bytes(5, b"") +
        _pb_str(7, "default")
    )

    return (
        _pb_str(1, mission_uuid) +
        _pb_str(2, mission_name) +
        _pb_msg(3, channel_container) +
        _pb_msg(4, server_msg)
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
    return "\n".join([
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
    ])


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

    channel_name = str(channels[0]).strip()
    channel_uuid = str(uuid.uuid4())

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
        "channels": [
            {
                "id": channel_uuid,
                "name": channel_name,
                "host": f"{fqdn}:{int(voice_port)}",
                "missionId": mission_uuid,
                "serverChannelId": 1,
                "subtitle": channel_name,
                "isMumble": True,
                "isEngineering": False,
                "port": -1,
            }
        ],
        "missionType": "COMBINED",
        "missionIP": "",
        "missionPort": "-1",
        "missionDefaultProtocol": "UDP",
    }

    proto_bytes = _build_vx_proto(
        mission_uuid=mission_uuid,
        mission_name=mission_label,
        channel_uuid=channel_uuid,
        channel_name=channel_name,
        server_uuid=server_uuid,
        fqdn=fqdn,
        port=int(voice_port),
        subtitle=channel_name,
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
        "target": {
            "callsign": target_callsign,
            "uid": target_uid,
        },
        "sender": {
            "callsign": sender_callsign,
            "uid": sender_uid,
        },
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
        "entries": [
            "MANIFEST/manifest.xml",
            json_entry,
            proto_entry,
        ],
        "manifest_name": manifest_name,
        "mission_uuid": mission_uuid,
    }


def _multipart_body(field_name: str, filename: str, content: bytes, content_type: str) -> tuple[str, bytes]:
    boundary = f"----martine-{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        f"\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return boundary, head + content + tail


def _parse_upload_hash(resp_text: str) -> str:
    m = HASH_RE.search(resp_text or "")
    if m:
        return str(m.group(1))
    try:
        raw = json.loads(resp_text)
        if isinstance(raw, dict):
            for key in ("hash", "sha256"):
                val = str(raw.get(key) or "").strip()
                if val:
                    return val
    except Exception:
        pass
    raise RuntimeError(f"could not parse missionupload hash from response: {resp_text[:500]}")


def _upload_package_https(
    *,
    tak_host: str,
    zip_path: Path,
    response_path: Path,
) -> str:
    body_boundary, body = _multipart_body(
        "assetfile",
        zip_path.name,
        zip_path.read_bytes(),
        "application/zip",
    )
    path = f"/Marti/sync/missionupload?filename={quote(zip_path.name)}"
    ctx = _mtls_context()

    conn = http.client.HTTPSConnection(
        host=str(tak_host),
        port=LOCAL_MARTI_HTTPS_PORT,
        context=ctx,
        timeout=30,
    )
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={body_boundary}",
                "Content-Length": str(len(body)),
            },
        )
        resp = conn.getresponse()
        resp_status = int(resp.status)
        resp_text = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()

    _write_text(response_path, resp_text)

    if resp_status >= 400:
        raise RuntimeError(f"missionupload failed: HTTP {resp_status}: {resp_text[:500]}")

    return _parse_upload_hash(resp_text)



def _wait_for_uploaded_content(
    *,
    tak_host: str,
    marti_hash: str,
    timeout_seconds: float = 5.0,
    interval_seconds: float = 0.25,
) -> dict[str, Any]:
    path = f"/Marti/sync/content?hash={quote(marti_hash)}"
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    attempts = 0
    last_error = ""

    while True:
        attempts += 1
        ctx = _mtls_context()
        conn = http.client.HTTPSConnection(
            host=str(tak_host),
            port=LOCAL_MARTI_HTTPS_PORT,
            context=ctx,
            timeout=10,
        )
        try:
            conn.request("GET", path, headers={"Accept": "*/*"})
            resp = conn.getresponse()
            body = resp.read()
            if 200 <= int(resp.status) < 300 and body is not None:
                return {
                    "ok": True,
                    "status": int(resp.status),
                    "attempts": attempts,
                    "bytes": len(body),
                    "path": path,
                }
            last_error = f"HTTP {resp.status}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.05, float(interval_seconds)))

    raise RuntimeError(
        f"uploaded content not readable yet after {attempts} attempts for hash {marti_hash}: {last_error}"
    )


def _build_fileshare_xml(
    *,
    dest_callsign: str,
    dest_uid: str = "",
    sender_uid: str,
    sender_callsign: str,
    display_name: str,
    display_filename: str,
    sender_url: str,
    package_size: int,
    package_hash: str,
    stale_hours: int = 2,
) -> tuple[str, str]:
    event_uid = str(uuid.uuid4()).lower()
    ack_uid = str(uuid.uuid4()).lower()
    now = _utc_now()
    time_now = _iso_z(now)
    time_stale = _iso_z(now + timedelta(hours=max(1, int(stale_hours or 2))))

    dest_attrs: list[str] = []
    if str(dest_uid or "").strip():
        dest_attrs.append(f'uid="{escape(str(dest_uid).strip())}"')
    if str(dest_callsign or "").strip():
        dest_attrs.append(f'callsign="{escape(str(dest_callsign).strip())}"')
    dest_xml = f"    <marti><dest {' '.join(dest_attrs)}/></marti>\n" if dest_attrs else ""

    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        f"<event version='2.0' uid='{escape(event_uid)}' type='b-f-t-r' time='{time_now}' start='{time_now}' stale='{time_stale}' how='h-e'>\n"
        f"  <point lat='{DEFAULT_LAT}' lon='{DEFAULT_LON}' hae='{DEFAULT_HAE}' ce='{DEFAULT_CE}' le='{DEFAULT_LE}' />\n"
        "  <detail>\n"
        f"    <fileshare filename=\"{escape(display_filename)}\" senderUrl=\"{escape(sender_url)}\" sizeInBytes=\"{int(package_size)}\" sha256=\"{escape(package_hash)}\" senderUid=\"{escape(sender_uid)}\" senderCallsign=\"{escape(sender_callsign)}\" name=\"{escape(display_name)}\"/>\n"
        f"    <ackrequest uid=\"{escape(ack_uid)}\" ackrequested=\"true\" tag=\"{escape(display_name)}\"/>\n"
        f"{dest_xml}"
        "  </detail>\n"
        "</event>\n"
    )
    return event_uid, xml



def _wait_for_cot_router_event(
    *,
    event_uid: str,
    timeout_seconds: float = 8.0,
    interval_seconds: float = 0.25,
) -> dict[str, Any]:
    from takctl.services.db.client import DB  # type: ignore

    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    attempts = 0
    sql = (
        "SELECT id, uid, cot_type, servertime "
        "FROM cot_router "
        "WHERE uid = %s "
        "ORDER BY servertime DESC "
        "LIMIT 1"
    )

    try:
        with DB() as db:
            while True:
                attempts += 1
                try:
                    row = db.query_one(sql, (event_uid,))
                except Exception as e:
                    return {
                        "ok": False,
                        "status": "probe_error",
                        "attempts": attempts,
                        "uid": event_uid,
                        "error": f"{type(e).__name__}: {e}",
                    }

                if row:
                    return {
                        "ok": True,
                        "status": "observed",
                        "attempts": attempts,
                        "id": row.get("id"),
                        "uid": row.get("uid"),
                        "cot_type": row.get("cot_type"),
                        "servertime": str(row.get("servertime") or ""),
                    }

                if time.monotonic() >= deadline:
                    break
                time.sleep(max(0.05, float(interval_seconds)))

    except Exception as e:
        return {
            "ok": False,
            "status": "probe_error",
            "attempts": attempts,
            "uid": event_uid,
            "error": f"{type(e).__name__}: {e}",
        }

    return {
        "ok": False,
        "status": "not_observed",
        "attempts": attempts,
        "uid": event_uid,
    }


def _send_cot_tls(
    *,
    xml_text: str,
    host: str,
    port: int = LOCAL_COT_TLS_PORT,
) -> None:
    ctx = _mtls_context()
    payload = xml_text.encode("utf-8")

    with socket.create_connection((host, int(port)), timeout=15) as raw:
        with ctx.wrap_socket(raw, server_hostname=str(host)) as sock:
            _LOG.info(
                "voice_onboarding cot_tls_connected host=%s port=%s tls=%s cipher=%s",
                host,
                port,
                sock.version(),
                sock.cipher(),
            )

            # Test hypothesis: server/app-layer may emit something immediately after handshake.
            pre_recv_len = 0
            try:
                sock.settimeout(0.35)
                pre = sock.recv(4096)
                pre_recv_len = len(pre or b"")
            except socket.timeout:
                pre_recv_len = 0
            except Exception as e:
                _LOG.info(
                    "voice_onboarding cot_tls_pre_recv_error host=%s port=%s err=%s",
                    host,
                    port,
                    f"{type(e).__name__}: {e}",
                )
            finally:
                try:
                    sock.settimeout(15)
                except Exception:
                    pass

            _LOG.info(
                "voice_onboarding cot_tls_pre_send host=%s port=%s pre_recv_len=%s payload_len=%s",
                host,
                port,
                pre_recv_len,
                len(payload),
            )

            # Small settle delay to test whether immediate send/close is the race.
            time.sleep(0.20)
            sock.sendall(payload)
            _LOG.info(
                "voice_onboarding cot_tls_sent host=%s port=%s payload_len=%s",
                host,
                port,
                len(payload),
            )

            # Keep socket alive briefly after send so server can process before FIN.
            time.sleep(0.50)

            post_recv_len = 0
            try:
                sock.settimeout(0.35)
                post = sock.recv(4096)
                post_recv_len = len(post or b"")
            except socket.timeout:
                post_recv_len = 0
            except Exception as e:
                _LOG.info(
                    "voice_onboarding cot_tls_post_recv_error host=%s port=%s err=%s",
                    host,
                    port,
                    f"{type(e).__name__}: {e}",
                )
            finally:
                try:
                    sock.settimeout(15)
                except Exception:
                    pass

            _LOG.info(
                "voice_onboarding cot_tls_post_send host=%s port=%s post_recv_len=%s",
                host,
                port,
                post_recv_len,
            )


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
                    "Om ATAK/Vx frågar efter Mumble-lösenord, skriv in serverlösenordet som visas här."
                ]
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

        _send_cot_tls(
            xml_text=xml_text,
            host=LOCAL_COT_TLS_HOST,
            port=LOCAL_COT_TLS_PORT,
        )

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
