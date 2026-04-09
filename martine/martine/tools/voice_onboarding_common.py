from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from takctl.config import load_config, load_secrets
from takctl.config import load_secrets


IDENTITY_DIR = Path("/opt/tak/tools/martine/runtime/identity")
CERT_PEM = IDENTITY_DIR / "client.pem"
KEY_PEM = IDENTITY_DIR / "client.key"
CA_PEM = IDENTITY_DIR / "ca.pem"

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
    for cand in (
        _cfg_get(cfg, "fqdn", ""),
        _cfg_get(cfg, "tak_public_host", ""),
        _cfg_get(cfg, "public_host", ""),
    ):
        s = str(cand or "").strip().lower()
        if s:
            return s

    for path in (
        Path("/opt/tak/tools/takctl/conf.d/node.conf"),
        Path("/opt/tak/tools/takctl/conf.d/core.conf"),
    ):
        rows = _read_simple_kv(path)
        fqdn = str(rows.get("fqdn") or "").strip().lower()
        if fqdn:
            return fqdn

    raise RuntimeError("missing fqdn in martine config and /opt/tak/tools/takctl/conf.d")


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

    for part in str(channels_csv or "").split(","):
        add(part)

    defs = defaults or {}
    raw_defaults = defs.get("channels")
    if isinstance(raw_defaults, str):
        for part in raw_defaults.split(","):
            add(part)
    elif isinstance(raw_defaults, Iterable):
        for item in raw_defaults:
            if isinstance(item, dict):
                add(item.get("name") or item.get("path") or item.get("channel"))
            else:
                add(item)

    if not out:
        out.append("Root")
    return out


def _normalize_server(defaults: dict[str, Any], host: str, ipv4: str) -> dict[str, Any]:
    server = defaults.get("server")
    if not isinstance(server, dict):
        server = {}

    return {
        "label": _first_nonempty(server.get("label"), _host_token(host)),
        "host": _first_nonempty(server.get("host"), host),
        "ipv4": _first_nonempty(server.get("ipv4"), ipv4),
        "port": int(server.get("port") or 64738),
        "username": _first_nonempty(server.get("username"), "atak"),
        "password": _first_nonempty(server.get("password"), ""),
    }


def _normalize_identity(defaults: dict[str, Any]) -> dict[str, Any]:
    ident = defaults.get("identity")
    if not isinstance(ident, dict):
        ident = {}
    return {
        "callsign_prefix": _first_nonempty(ident.get("callsign_prefix"), "VX"),
        "uid_prefix": _first_nonempty(ident.get("uid_prefix"), "ANDROID-"),
    }


def _normalize_position(defaults: dict[str, Any]) -> dict[str, str]:
    pos = defaults.get("position")
    if not isinstance(pos, dict):
        pos = {}
    return {
        "lat": _first_nonempty(pos.get("lat"), DEFAULT_LAT),
        "lon": _first_nonempty(pos.get("lon"), DEFAULT_LON),
        "hae": _first_nonempty(pos.get("hae"), DEFAULT_HAE),
        "ce": _first_nonempty(pos.get("ce"), DEFAULT_CE),
        "le": _first_nonempty(pos.get("le"), DEFAULT_LE),
    }


def _build_defaults(cfg: Any) -> dict[str, Any]:
    defaults = _load_defaults()
    host = _resolve_fqdn(cfg)
    ipv4 = _resolve_ipv4(host)

    return {
        "server": _normalize_server(defaults, host, ipv4),
        "identity": _normalize_identity(defaults),
        "position": _normalize_position(defaults),
        "channels": _normalize_channels(defaults=defaults),
        "raw": defaults,
    }



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
    return _tls_context()


def _tls_context() -> ssl.SSLContext:
    if not CERT_PEM.exists():
        raise RuntimeError(f"missing client cert: {CERT_PEM}")
    if not KEY_PEM.exists():
        raise RuntimeError(f"missing client key: {KEY_PEM}")
    if not CA_PEM.exists():
        raise RuntimeError(f"missing CA pem: {CA_PEM}")

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
    raise RuntimeError(f"could not parse missionupload hash from response: {str(resp_text)[:500]}")




def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _xml_escape(text: Any) -> str:
    s = str(text or "")
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _new_uid(prefix: str = "ANDROID-") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12].upper()}"


def _now_z() -> str:
    return _iso_z(_utc_now())
