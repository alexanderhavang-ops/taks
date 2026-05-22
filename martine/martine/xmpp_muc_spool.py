from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any


_DEFAULT_STATE_DIR = Path("/opt/tak/tools/martine/state")
_DEFAULT_SPOOL_DIR = _DEFAULT_STATE_DIR / "xmpp-muc"

_SAFE_ROOM_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _spool_dir() -> Path:
    return Path(os.environ.get("MARTINE_XMPP_MUC_SPOOL_DIR", str(_DEFAULT_SPOOL_DIR)))


def _own_nicks(extra: set[str] | None = None) -> set[str]:
    raw = os.environ.get(
        "MARTINE_XMPP_OWN_NICKS",
        "martine,Martine,MARTINE,ANDROID-MARTINE",
    )
    out = {x.strip() for x in raw.split(",") if x.strip()}
    for x in extra or set():
        x = str(x or "").strip()
        if x:
            out.add(x)
    return out


def _jid_part(value: Any, attr: str) -> str:
    try:
        v = getattr(value, attr)
        if v is not None:
            return str(v)
    except Exception:
        pass
    return ""


def _message_get(msg: Any, key: str) -> Any:
    try:
        return msg[key]
    except Exception:
        pass
    try:
        return msg.get(key)
    except Exception:
        return None


def _room_name(room_jid: str) -> str:
    local = room_jid.split("@", 1)[0].strip() or "unknown"
    local = _SAFE_ROOM_RE.sub("_", local).strip("._-")
    return local or "unknown"


def _esc(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def maybe_spool_xmpp_muc_message(msg: Any, *, own_nicks: set[str] | None = None) -> bool:
    """Append one inbound XMPP MUC/groupchat message as compact TSV.

    Format:
        epoch_ms<TAB>nick<TAB>body_escaped<LF>

    File:
        $MARTINE_XMPP_MUC_SPOOL_DIR/<room>.tsv
    """
    typ = str(_message_get(msg, "type") or "").strip().lower()
    if typ != "groupchat":
        return False

    body = str(_message_get(msg, "body") or "")
    if not body.strip():
        return False

    frm = _message_get(msg, "from")
    room_jid = _jid_part(frm, "bare") or str(frm or "").split("/", 1)[0]
    nick = _jid_part(frm, "resource") or str(frm or "").split("/", 1)[-1]

    if not nick:
        nick = "unknown"

    if nick in _own_nicks(own_nicks):
        return False

    base = _spool_dir()
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o750)
    except PermissionError:
        pass

    path = base / f"{_room_name(room_jid)}.tsv"
    epoch_ms = int(time.time() * 1000)
    line = f"{epoch_ms}\t{_esc(nick)}\t{_esc(body)}\n".encode("utf-8")

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)

    return True
