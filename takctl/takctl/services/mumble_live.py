from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import time


MARTINE_VENV_PYTHON = Path("/opt/tak/tools/martine/.venv/bin/python")

VOICE_CONF_CANDIDATES = [
    Path("/opt/tak/tools/takctl/conf.d/martine_voice.conf"),
]

# Viktigt: använd inte bootstrap-hemligheten här.
PASSWORD_CANDIDATES = [
    Path("/opt/tak/tools/takctl/secrets.d/murmur.conf"),
    Path("/etc/mumble-server.ini"),
]

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out

    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception:
        return out

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _load_server_password() -> str:
    for p in PASSWORD_CANDIDATES:
        kv = _read_kv(p)
        pw = str(kv.get("serverpassword", "")).strip()
        if pw:
            return pw
    raise RuntimeError("serverpassword not found in takctl secrets or readable mumble-server config")


def _load_host_port() -> tuple[str, int]:
    host = "127.0.0.1"
    port = 64738

    for p in VOICE_CONF_CANDIDATES:
        kv = _read_kv(p)
        h = str(kv.get("host", "")).strip()
        if h:
            host = h

        raw_port = str(kv.get("port", "")).strip()
        if raw_port:
            try:
                port = int(raw_port)
            except ValueError:
                pass

        break

    return host, port


def _probe_script() -> str:
    return r"""
from __future__ import annotations

import json
import os
import re
import time
import ssl

# Python 3.12 removed ssl.wrap_socket. pymumble_py3 still calls it.
# Keep this shim close to the probe script because the probe is executed
# inside the Martine venv and must work on Ubuntu 24.04 / Python 3.12.
if not hasattr(ssl, "wrap_socket"):
    def _pymumble_wrap_socket(sock, keyfile=None, certfile=None, server_side=False, cert_reqs=ssl.CERT_NONE,
                             ssl_version=ssl.PROTOCOL_TLS_CLIENT, ca_certs=None, do_handshake_on_connect=True,
                             suppress_ragged_eofs=True, ciphers=None):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = cert_reqs
        if ciphers:
            try:
                ctx.set_ciphers(ciphers)
            except Exception:
                pass
        if certfile or keyfile:
            ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        if ca_certs:
            ctx.load_verify_locations(ca_certs)
        return ctx.wrap_socket(sock, server_hostname=None, do_handshake_on_connect=do_handshake_on_connect)
    ssl.wrap_socket = _pymumble_wrap_socket


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _import_pymumble():
    try:
        import pymumble_py3 as pymumble_py3
        return pymumble_py3
    except Exception:
        import pymumble.pymumble_py3 as pymumble_py3
        return pymumble_py3


def _norm_token(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _suffix_kind(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _UUID_RE.match(raw):
        return "uuid_like"
    if raw.upper().startswith("ANDROID-"):
        return "android_like"
    norm = _norm_token(raw)
    if len(norm) >= 12 and all(ch in "0123456789abcdef" for ch in norm):
        return "hex_like"
    return "other"


def _likely_client_uid_format(value: str) -> bool:
    kind = _suffix_kind(value)
    return kind in ("uuid_like", "android_like", "hex_like")


def _channel_id(ch):
    if ch is None:
        return None
    for key in ("channel_id", "id"):
        try:
            v = ch[key]
            if v is not None:
                return int(v)
        except Exception:
            pass
        try:
            v = ch.get_property(key)
            if v is not None:
                return int(v)
        except Exception:
            pass
    return None


def _channel_name(ch):
    if ch is None:
        return ""
    for key in ("name", "channel_name"):
        try:
            v = ch[key]
            if v is not None:
                return str(v)
        except Exception:
            pass
        try:
            v = ch.get_property(key)
            if v is not None:
                return str(v)
        except Exception:
            pass
    return ""


def _user_channel_id(user):
    if user is None:
        return None
    for key in ("channel_id",):
        try:
            v = user[key]
            if v is not None:
                return int(v)
        except Exception:
            pass
        try:
            v = user.get_property(key)
            if v is not None:
                return int(v)
        except Exception:
            pass
    return None


def _user_name(user):
    if user is None:
        return ""
    for key in ("name", "username"):
        try:
            v = user[key]
            if v is not None:
                return str(v)
        except Exception:
            pass
        try:
            v = user.get_property(key)
            if v is not None:
                return str(v)
        except Exception:
            pass
    return ""


def _user_session(user):
    if user is None:
        return None
    for key in ("session", "session_id"):
        try:
            v = user[key]
            if v is not None:
                return int(v)
        except Exception:
            pass
        try:
            v = user.get_property(key)
            if v is not None:
                return int(v)
        except Exception:
            pass
    return None


def _split_name(raw_name: str) -> dict:
    raw = str(raw_name or "").strip()
    callsign = raw
    suffix = ""
    name_kind = "plain"

    if "---" in raw:
        left, right = raw.split("---", 1)
        callsign = left.strip()
        suffix = right.strip()
        name_kind = "callsign_suffix"

    return {
        "raw_name": raw,
        "callsign": callsign,
        "callsign_norm": _norm_token(callsign),
        "suffix_candidate": suffix,
        "suffix_norm": _norm_token(suffix),
        "suffix_kind": _suffix_kind(suffix),
        "likely_client_uid_format": _likely_client_uid_format(suffix),
        "name_kind": name_kind,
    }


def main():
    pymumble_py3 = _import_pymumble()

    host = os.environ["MUMBLE_HOST"]
    port = int(os.environ.get("MUMBLE_PORT", "64738"))
    password = os.environ["MUMBLE_SERVER_PASSWORD"]
    username = os.environ.get("MUMBLE_PROBE_USERNAME", "takctl-mumble-dump")

    out = {
        "meta": {
            "source": "martine-venv-pymumble",
        },
        "server": {
            "host": host,
            "port": port,
            "connected": False,
        },
        "self": None,
        "channels": [],
        "users": [],
    }

    m = None
    try:
        m = pymumble_py3.Mumble(host, username, password=password, port=port)
        try:
            m.set_receive_sound(False)
        except Exception:
            pass

        m.start()
        m.is_ready()
        time.sleep(1.2)

        out["server"]["connected"] = True

        current = None
        try:
            current = m.my_channel()
        except Exception:
            current = None

        out["self"] = {
            "channel_id": _channel_id(current),
            "channel_name": _channel_name(current),
        }

        channel_rows = []
        try:
            chans = list(m.channels.values())
        except Exception:
            chans = []

        for ch in chans:
            channel_rows.append(
                {
                    "channel_id": _channel_id(ch),
                    "name": _channel_name(ch),
                }
            )
        channel_rows.sort(key=lambda x: ((x["channel_id"] is None), x["channel_id"] or 0, x["name"] or ""))
        out["channels"] = channel_rows

        channel_name_by_id = {
            int(x["channel_id"]): str(x["name"] or "")
            for x in channel_rows
            if x.get("channel_id") is not None
        }

        user_rows = []
        try:
            users = list(m.users.values())
        except Exception:
            users = []

        for user in users:
            raw_name = _user_name(user)
            ch_id = _user_channel_id(user)
            split = _split_name(raw_name)
            user_rows.append(
                {
                    "name": raw_name,
                    "callsign": split["callsign"],
                    "callsign_norm": split["callsign_norm"],
                    "suffix_candidate": split["suffix_candidate"],
                    "suffix_norm": split["suffix_norm"],
                    "suffix_kind": split["suffix_kind"],
                    "likely_client_uid_format": split["likely_client_uid_format"],
                    "name_kind": split["name_kind"],
                    "session": _user_session(user),
                    "channel_id": ch_id,
                    "channel_name": channel_name_by_id.get(ch_id, ""),
                    "connected_now": True,
                }
            )

        user_rows.sort(
            key=lambda x: (
                (x["channel_id"] is None),
                x["channel_id"] or 0,
                x["callsign"] or "",
                x["name"] or "",
            )
        )
        out["users"] = user_rows

        print(json.dumps(out, indent=2, ensure_ascii=False))
    finally:
        if m is not None:
            try:
                m.stop()
            except Exception:
                pass


if __name__ == "__main__":
    main()
"""



_MUMBLE_LIVE_CACHE = None
_MUMBLE_LIVE_CACHE_TS = 0.0
_MUMBLE_LIVE_CACHE_TTL = 0.0


def _mumble_live_clone(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(json.dumps(data or {}, ensure_ascii=False, default=str))
    except Exception:
        return dict(data or {})


def _mumble_live_cache_get() -> Dict[str, Any] | None:
    global _MUMBLE_LIVE_CACHE, _MUMBLE_LIVE_CACHE_TS, _MUMBLE_LIVE_CACHE_TTL

    if _MUMBLE_LIVE_CACHE is None:
        return None

    age = time.monotonic() - float(_MUMBLE_LIVE_CACHE_TS or 0.0)
    ttl = float(_MUMBLE_LIVE_CACHE_TTL or 0.0)
    if ttl <= 0 or age >= ttl:
        return None

    out = _mumble_live_clone(_MUMBLE_LIVE_CACHE)
    meta = dict(out.get("meta") or {})
    meta["generated_at"] = _utc_now_iso()
    meta["cache_hit"] = True
    meta["cache_age_sec"] = int(age)
    meta["cache_ttl_sec"] = int(ttl)
    out["meta"] = meta
    return out


def _mumble_live_cache_store(data: Dict[str, Any], *, ttl_sec: int) -> None:
    global _MUMBLE_LIVE_CACHE, _MUMBLE_LIVE_CACHE_TS, _MUMBLE_LIVE_CACHE_TTL

    _MUMBLE_LIVE_CACHE = _mumble_live_clone(data)
    _MUMBLE_LIVE_CACHE_TS = time.monotonic()
    _MUMBLE_LIVE_CACHE_TTL = float(max(1, int(ttl_sec)))


def snapshot_mumble_live() -> Dict[str, Any]:
    cached = _mumble_live_cache_get()
    if cached is not None:
        return cached

    host, port = _load_host_port()

    out: Dict[str, Any] = {
        "meta": {
            "generated_at": _utc_now_iso(),
            "source": "takctl.services.mumble_live",
            "cache_hit": False,
        },
        "server": {
            "host": host,
            "port": port,
            "connected": False,
        },
        "self": None,
        "channels": [],
        "users": [],
    }

    if not MARTINE_VENV_PYTHON.exists():
        out["error"] = f"missing martine python: {MARTINE_VENV_PYTHON}"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    try:
        password = _load_server_password()
    except Exception as e:
        out["error"] = f"password load failed: {type(e).__name__}: {e}"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    env = dict(os.environ)
    env["MUMBLE_HOST"] = str(host)
    env["MUMBLE_PORT"] = str(port)
    env["MUMBLE_SERVER_PASSWORD"] = password
    env["MUMBLE_PROBE_USERNAME"] = "takctl-mumble-dump"

    try:
        p = subprocess.run(
            [str(MARTINE_VENV_PYTHON), "-c", _probe_script()],
            text=True,
            capture_output=True,
            env=env,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        out["error"] = "mumble live probe timed out"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out
    except Exception as e:
        out["error"] = f"mumble live probe failed: {type(e).__name__}: {e}"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    stdout = (p.stdout or "").strip()
    stderr = (p.stderr or "").strip()

    if p.returncode != 0:
        out["error"] = stderr or stdout or f"probe failed with rc={p.returncode}"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    if not stdout:
        out["error"] = "probe returned empty output"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    try:
        parsed = json.loads(stdout)
    except Exception as e:
        out["error"] = f"invalid probe json: {type(e).__name__}: {e}"
        out["probe_stdout"] = stdout[-4000:]
        if stderr:
            out["probe_stderr"] = stderr[-2000:]
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    if not isinstance(parsed, dict):
        out["error"] = "probe output was not a json object"
        _mumble_live_cache_store(out, ttl_sec=60)
        return out

    parsed_meta = dict(parsed.get("meta") or {})
    parsed_meta["generated_at"] = _utc_now_iso()
    parsed_meta["source"] = "takctl.services.mumble_live"
    parsed_meta["cache_hit"] = False
    parsed["meta"] = parsed_meta

    server = dict(parsed.get("server") or {})
    channels = list(parsed.get("channels") or [])
    users = list(parsed.get("users") or [])

    # A real synchronized Mumble view should at least contain Root.
    # If Murmur has globally banned the local probe, PyMumble can still make this
    # look half-connected while returning an empty tree. Treat that as failed and
    # cache the failure long enough to stop feeding the ban loop.
    if bool(server.get("connected")) and len(channels) == 0:
        server["connected"] = False
        parsed["server"] = server
        parsed["error"] = (
            parsed.get("error")
            or "mumble live probe returned zero channels; likely not synchronized or localhost is temporarily globally banned"
        )
        _mumble_live_cache_store(parsed, ttl_sec=60)
        return parsed

    # Normal success: cache briefly so the UI poller does not create a new
    # authenticated Mumble connection for every status/card/detail request.
    _mumble_live_cache_store(parsed, ttl_sec=30)
    return parsed
