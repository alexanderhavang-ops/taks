from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Iterable


VOICE_CONF_CANDIDATES = [
    Path("/opt/tak/tools/takctl/conf.d/martine_voice.conf"),
]

SECRETS_CANDIDATES = [
    # Viktigt: runtime/takctl först, inte bootstrap.
    Path("/opt/tak/tools/takctl/secrets.d/murmur.conf"),
    Path("/opt/tak/bootstrap/secrets.d/murmur.conf"),
]

MARTINE_PYTHON = Path("/opt/tak/tools/martine/.venv/bin/python")


def _read_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def _norm(v: Any) -> str:
    return str(v or "").strip().upper()


def _voice_name_stem(name: Any) -> str:
    """
    VX/Mumble-namn ser ut ungefär:
      EAQQ2---4e4eaef4-0ec9-45c2-bb27-16955e181191

    Vi behandlar delen före --- som callsign-stammen.
    Delen efter --- betraktas INTE som auktoritativ client_uid.
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    if "---" in raw:
        raw = raw.split("---", 1)[0]
    return _norm(raw)


def _voice_name_suffix(name: Any) -> str:
    raw = str(name or "").strip()
    if not raw or "---" not in raw:
        return ""
    return str(raw.split("---", 1)[1] or "").strip()


def _load_voice_server() -> dict[str, Any]:
    host = "127.0.0.1"
    port = 64738

    for path in VOICE_CONF_CANDIDATES:
        kv = _read_kv(path)
        if not kv:
            continue

        if str(kv.get("host", "")).strip():
            host = str(kv.get("host", "")).strip()

        raw_port = str(kv.get("port", "")).strip()
        if raw_port:
            try:
                port = int(raw_port)
            except Exception:
                pass

        break

    return {
        "host": host,
        "port": int(port),
    }


def _load_server_password() -> str:
    for path in SECRETS_CANDIDATES:
        kv = _read_kv(path)
        pw = str(kv.get("serverpassword", "")).strip()
        if pw:
            return pw
    return ""


def _extract_json_blob(text: str) -> dict[str, Any]:
    s = str(text or "").strip()
    if not s:
        return {}

    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < start:
        return {}

    blob = s[start : end + 1]
    try:
        data = json.loads(blob)
    except Exception:
        return {}

    if isinstance(data, dict):
        return data
    return {}


def _live_dump_script() -> str:
    return textwrap.dedent(
        r'''
        from __future__ import annotations

        import json
        import sys
        import time

        host = str(sys.argv[1])
        port = int(sys.argv[2])
        password = str(sys.argv[3])

        out = {
            "server": {
                "host": host,
                "port": port,
                "connected": False,
            },
            "self": {},
            "channels": [],
            "users": [],
        }

        def _safe_int(v):
            try:
                return int(v)
            except Exception:
                return None

        def _get_from_obj(obj, *names):
            for name in names:
                try:
                    if isinstance(obj, dict) and name in obj:
                        return obj[name]
                except Exception:
                    pass
                try:
                    return obj[name]
                except Exception:
                    pass
                try:
                    value = getattr(obj, name)
                    if callable(value):
                        continue
                    return value
                except Exception:
                    pass
                try:
                    value = obj.get_property(name)
                    if value is not None:
                        return value
                except Exception:
                    pass
            return None

        def _channel_id(ch):
            return _safe_int(_get_from_obj(ch, "channel_id", "id"))

        def _channel_name(ch):
            v = _get_from_obj(ch, "name", "channel_name")
            return str(v or "").strip()

        def _user_name(u):
            v = _get_from_obj(u, "name", "username")
            return str(v or "").strip()

        def _user_session(u):
            return _safe_int(_get_from_obj(u, "session"))

        def _user_channel_id(u):
            return _safe_int(_get_from_obj(u, "channel_id"))

        mumble = None
        try:
            import pymumble_py3 as pymumble

            mumble = pymumble.Mumble(
                host,
                "takctl-mumble-dump",
                password=password,
                port=port,
            )
            mumble.set_receive_sound(False)
            mumble.start()
            mumble.is_ready()

            time.sleep(1.0)

            out["server"]["connected"] = True

            try:
                my_channel = mumble.my_channel()
                out["self"] = {
                    "channel_id": _channel_id(my_channel),
                    "channel_name": _channel_name(my_channel),
                }
            except Exception:
                out["self"] = {}

            try:
                channels = []
                for _k, ch in getattr(mumble, "channels", {}).items():
                    channels.append({
                        "channel_id": _channel_id(ch),
                        "name": _channel_name(ch),
                    })
                channels.sort(key=lambda x: (x["channel_id"] is None, x["channel_id"] or 0, x["name"] or ""))
                out["channels"] = channels
            except Exception:
                out["channels"] = []

            channel_name_by_id = {}
            for ch in out["channels"]:
                cid = ch.get("channel_id")
                if cid is not None:
                    channel_name_by_id[int(cid)] = str(ch.get("name") or "")

            try:
                users = []
                for _k, user in getattr(mumble, "users", {}).items():
                    cid = _user_channel_id(user)
                    users.append({
                        "name": _user_name(user),
                        "session": _user_session(user),
                        "channel_id": cid,
                        "channel_name": channel_name_by_id.get(cid, ""),
                    })
                users.sort(key=lambda x: ((x["channel_name"] or ""), (x["name"] or ""), x["session"] or 0))
                out["users"] = users
            except Exception:
                out["users"] = []

        except Exception as e:
            out["server"]["connected"] = False
            out["server"]["error"] = f"{type(e).__name__}: {e}"
        finally:
            if mumble is not None:
                try:
                    mumble.stop()
                except Exception:
                    pass

        print(json.dumps(out, indent=2, ensure_ascii=False))
        '''
    ).strip()


def fetch_live_voice_dump(timeout_sec: int = 8) -> dict[str, Any]:
    server = _load_voice_server()
    password = _load_server_password()

    fallback = {
        "server": {
            "host": server["host"],
            "port": int(server["port"]),
            "connected": False,
        },
        "self": {},
        "channels": [],
        "users": [],
    }

    if not password:
        fallback["server"]["error"] = "missing serverpassword"
        return fallback

    if not MARTINE_PYTHON.exists():
        fallback["server"]["error"] = f"missing martine python: {MARTINE_PYTHON}"
        return fallback

    try:
        proc = subprocess.run(
            [
                str(MARTINE_PYTHON),
                "-c",
                _live_dump_script(),
                str(server["host"]),
                str(server["port"]),
                password,
            ],
            text=True,
            capture_output=True,
            timeout=max(1, int(timeout_sec)),
            check=False,
        )
    except Exception as e:
        fallback["server"]["error"] = f"{type(e).__name__}: {e}"
        return fallback

    data = _extract_json_blob((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if not isinstance(data, dict) or not data:
        fallback["server"]["error"] = f"live dump returned no json (rc={proc.returncode})"
        return fallback

    try:
        data.setdefault("server", {})
        data["server"].setdefault("host", server["host"])
        data["server"].setdefault("port", int(server["port"]))
        data.setdefault("self", {})
        data.setdefault("channels", [])
        data.setdefault("users", [])
    except Exception:
        return fallback

    return data


def _candidate_names_for_row(row: dict[str, Any]) -> tuple[set[str], set[str]]:
    """
    Returnerar:
      - generella matchnamn (username, callsign, observed callsign)
      - uid-liknande kandidatvärden för svag suffixmatch
    """
    names: set[str] = set()
    uidish: set[str] = set()

    header = dict((row or {}).get("header") or {})
    identity = dict((row or {}).get("identity") or {})
    devices = list((row or {}).get("devices") or [])
    user = dict((row or {}).get("user") or {})

    for v in (
        (row or {}).get("username"),
        header.get("username"),
        user.get("username"),
        header.get("callsign"),
        identity.get("callsign"),
        identity.get("name"),
    ):
        nv = _norm(v)
        if nv:
            names.add(nv)

    for d in devices:
        for v in (
            d.get("observed_callsign"),
            d.get("callsign"),
        ):
            nv = _norm(v)
            if nv:
                names.add(nv)

        for v in (
            d.get("client_uid"),
            d.get("uid"),
            d.get("endpoint_id"),
        ):
            raw = str(v or "").strip()
            if raw:
                uidish.add(raw)

    return names, uidish


def _match_voice_users(row: dict[str, Any], voice_users: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_names, candidate_uidish = _candidate_names_for_row(row)
    matches: list[dict[str, Any]] = []

    for vu in voice_users:
        name = str((vu or {}).get("name") or "").strip()
        if not name:
            continue

        name_norm = _norm(name)
        stem = _voice_name_stem(name)
        suffix = _voice_name_suffix(name)

        reason = ""
        if name_norm and name_norm in candidate_names:
            reason = "exact_name"
        elif stem and stem in candidate_names:
            reason = "callsign_stem"
        elif suffix and suffix in candidate_uidish:
            reason = "suffix_uidish"

        if not reason:
            continue

        matches.append(
            {
                "name": name,
                "session": (vu or {}).get("session"),
                "channel_id": (vu or {}).get("channel_id"),
                "channel_name": str((vu or {}).get("channel_name") or "").strip(),
                "match_reason": reason,
            }
        )

    return matches


def _voice_block_for_row(row: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    voice_users = list((dump or {}).get("users") or [])
    matches = _match_voice_users(row, voice_users)

    channel_names: list[str] = []
    channel_ids: list[int] = []
    matched_names: list[str] = []
    match_reasons: list[str] = []

    for m in matches:
        matched_names.append(str(m.get("name") or ""))
        match_reasons.append(str(m.get("match_reason") or ""))
        ch_name = str(m.get("channel_name") or "").strip()
        ch_id = m.get("channel_id")

        if ch_name and ch_name not in channel_names:
            channel_names.append(ch_name)

        try:
            ch_id_int = int(ch_id)
        except Exception:
            ch_id_int = None

        if ch_id_int is not None and ch_id_int not in channel_ids:
            channel_ids.append(ch_id_int)

    connected_now = bool(matches)

    return {
        "server": {
            "host": str((((dump or {}).get("server") or {}).get("host") or "")),
            "port": int((((dump or {}).get("server") or {}).get("port") or 64738)),
            "connected": bool((((dump or {}).get("server") or {}).get("connected") is True)),
            "error": str((((dump or {}).get("server") or {}).get("error") or "")),
        },
        "user": {
            "connected_now": connected_now,
            "matched_user_names": matched_names,
            "match_reasons": match_reasons,
            "channel_names": channel_names,
            "channel_ids": channel_ids,
            "matches": matches,
        },
    }


def attach_voice_status(users_out: list[dict[str, Any]], timeout_sec: int = 8) -> dict[str, Any]:
    """
    Kör en live dump en gång och annoterar varje user-row med:
      row["voice"] = {
        "server": {...},
        "user": {
          "connected_now": bool,
          "matched_user_names": [...],
          "match_reasons": [...],
          "channel_names": [...],
          "channel_ids": [...],
          "matches": [...]
        }
      }

    Returnerar även en liten summary.
    """
    dump = fetch_live_voice_dump(timeout_sec=timeout_sec)
    connected_users = 0

    for row in users_out:
        vb = _voice_block_for_row(row, dump)
        row["voice"] = vb
        if ((vb.get("user") or {}).get("connected_now") is True):
            connected_users += 1

    return {
        "server": dict((dump or {}).get("server") or {}),
        "live_users": len(list((dump or {}).get("users") or [])),
        "matched_connected_users": connected_users,
    }
