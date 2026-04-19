from __future__ import annotations

import hashlib
import json
import socket
import ssl
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from martine.logging import get_logger, setup_martine_logging
from martine.state.paths import ensure_state_dirs, martine_state_dir


log = get_logger(__name__)

HOST = "127.0.0.1"
PORT = 8089

IDENTITY_DIR = "/opt/tak/tools/martine/runtime/identity"
CERT_PEM = f"{IDENTITY_DIR}/client.pem"
KEY_PEM = f"{IDENTITY_DIR}/client.key"
CA_PEM = f"{IDENTITY_DIR}/ca.pem"
CERT_METADATA = "/opt/tak/certs/cert-metadata.sh"
MARTINE_SECRETS_CONF = "/opt/tak/tools/takctl/secrets.d/martine.conf"
LEGACY_KEY_PASSWORD = "cert-pass-46-pass"

def _strip_quotes(v: str) -> str:
    s = str(v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s

def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return out
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return out
    for raw in lines:
        line = str(raw or "").strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        k, v = line.split("=", 1)
        key = str(k or "").strip()
        val = _strip_quotes(v)
        if key:
            out[key] = val
    return out

def _cert_password_candidates() -> list[str | None]:
    vals: list[str | None] = [None]

    martine_kv = _read_simple_kv(Path(MARTINE_SECRETS_CONF))
    for key in ("martine_client_p12_pass", "martine_truststore_p12_pass"):
        v = str(martine_kv.get(key, "") or "").strip()
        if v:
            vals.append(v)

    try:
        for raw in Path(CERT_METADATA).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("PASS="):
                continue
            v = line.split("=", 1)[1].strip()
            v = _strip_quotes(v)
            if v:
                vals.append(v)
            break
    except Exception:
        pass

    vals.append(LEGACY_KEY_PASSWORD)

    out: list[str | None] = []
    seen = set()
    for v in vals:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out

def _load_client_chain(ctx: ssl.SSLContext) -> None:
    last = None
    for pw in _cert_password_candidates():
        try:
            if pw is None:
                ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM)
            else:
                ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM, password=pw)
            return
        except (ssl.SSLError, OSError, ValueError) as e:
            last = e
    if last is not None:
        raise last
    ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM)


ALL_CHAT_ROOMS = "All Chat Rooms"

BOOTSTRAP_DELAY_SEC = 180
BOOTSTRAP_POLL_INTERVAL_SEC = 30
BOOTSTRAP_LOOKBACK_MINUTES = 240

TAKS_ONBOARDING_ROOT = Path("/opt/tak/takctl-state/onboarding")
DEVICE_STATE_ROOT = TAKS_ONBOARDING_ROOT / "devices"


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(value: Any) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif len(s) >= 3 and (s[-3] == "+" or s[-3] == "-") and s[-2:].isdigit():
            s = s + ":00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return None
    return json.loads(txt)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def cot_runtime_dir() -> Path:
    root = martine_state_dir()
    d = root / "cot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_takctl_importable() -> None:
    for p in (
        "/opt/tak/tools/takctl",
        "/opt/taks/takctl",
        "/opt/taks",
    ):
        if p not in sys.path and Path(p).exists():
            sys.path.append(p)


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stable_group_id(group_name: str, recipient_uid: str, chat_uid: str) -> str:
    payload = {
        "group_name": str(group_name or "").strip(),
        "members": sorted(
            [
                str(recipient_uid or "").strip(),
                str(chat_uid or "").strip(),
            ]
        ),
    }
    h = hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _strip_quotes(v: str) -> str:
    s = str(v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _read_kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return out

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out

    for line in lines:
        s = str(line or "").strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = str(k or "").strip()
        val = _strip_quotes(v)
        if key:
            out[key] = val
    return out


def _iter_kv_candidate_files() -> list[Path]:
    out: list[Path] = []

    def add_file(p: Path) -> None:
        if p.exists() and p.is_file() and p not in out:
            out.append(p)

    def add_dir(d: Path) -> None:
        if not d.exists() or not d.is_dir():
            return
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            name = p.name
            if name.startswith("."):
                continue
            if name.endswith(".template") or name.endswith(".example") or ".bak." in name:
                continue
            add_file(p)

    for root in (
        Path("/opt/taks/takctl"),
        Path("/opt/tak/tools/takctl"),
    ):
        add_file(root / "takctl.conf")
        add_file(root / "secrets.conf")
        add_dir(root / "conf.d")
        add_dir(root / "secrets.d")

    return out


def _cfg_first(cfg: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        v = str(cfg.get(key, "") or "").strip()
        if v:
            return v
    return default


def load_takctl_db_config() -> dict[str, Any]:
    merged: dict[str, str] = {}
    loaded_from: list[str] = []

    for path in _iter_kv_candidate_files():
        vals = _read_kv_file(path)
        if vals:
            merged.update(vals)
            loaded_from.append(str(path))

    host = _cfg_first(
        merged,
        "db_host",
        "pg_host",
        "postgres_host",
        default="127.0.0.1",
    )
    port_s = _cfg_first(
        merged,
        "db_port",
        "pg_port",
        "postgres_port",
        default="5432",
    )
    dbname = _cfg_first(
        merged,
        "db_name",
        "pg_database",
        "postgres_db",
        default="cot",
    )
    user = _cfg_first(
        merged,
        "db_user",
        "db_readonly_user",
        "db_ro_user",
        "readonly_db_user",
        "readonly_user",
        "pg_user",
        "postgres_user",
        default="takctl_ro",
    )
    password = _cfg_first(
        merged,
        "db_password",
        "db_readonly_password",
        "db_ro_password",
        "readonly_db_password",
        "readonly_password",
        "pg_password",
        "postgres_password",
        default="",
    )

    try:
        port = int(str(port_s or "5432").strip())
    except Exception:
        port = 5432

    cfg = {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
        "loaded_from": loaded_from,
    }

    redacted = dict(cfg)
    redacted["password"] = "***" if str(password or "").strip() else ""
    log.info("load_takctl_db_config cfg=%s", redacted)

    if not str(password or "").strip():
        log.warning("load_takctl_db_config_no_password cfg=%s", redacted)

    return cfg


def _pg_driver():
    try:
        import psycopg2  # type: ignore
        return ("psycopg2", psycopg2)
    except Exception:
        pass

    try:
        import psycopg  # type: ignore
        return ("psycopg", psycopg)
    except Exception:
        pass

    raise RuntimeError("Neither psycopg2 nor psycopg is installed")


def db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    try:
        _driver_name, driver = _pg_driver()
    except Exception as e:
        log.warning("db_rows_no_driver err=%s", e)
        return []

    cfg = load_takctl_db_config()

    conn_kwargs: dict[str, Any] = {
        "dbname": cfg.get("dbname") or "cot",
        "host": cfg.get("host") or "127.0.0.1",
        "port": int(cfg.get("port") or 5432),
        "user": cfg.get("user") or "takctl_ro",
    }
    if str(cfg.get("password") or "").strip():
        conn_kwargs["password"] = str(cfg.get("password") or "")

    try:
        conn = driver.connect(**conn_kwargs)
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                rows = cur.fetchall() or []
                return list(rows)
            finally:
                cur.close()
        finally:
            conn.close()
    except Exception as e:
        redacted = dict(conn_kwargs)
        if "password" in redacted:
            redacted["password"] = "***"
        log.warning("db_rows_failed sql=%r err=%s: %s", sql, redacted, e)
        return []


def db_scalar(sql: str, params: tuple[Any, ...] = ()) -> str:
    rows = db_rows(sql, params)
    if not rows:
        return ""
    row = rows[0]
    if not row:
        return ""
    return str(row[0] or "").strip()


def _extract_cn_from_subject_dn(subject_dn: str) -> str:
    s = str(subject_dn or "").strip()
    if not s:
        return ""
    for part in s.split(","):
        part = part.strip()
        if part.upper().startswith("CN="):
            return part[3:].strip()
    return ""


def resolve_username_for_client_uid(client_uid: str) -> str:
    uid = str(client_uid or "").strip()
    if not uid:
        return ""

    sql = """
        SELECT username
        FROM public.client_endpoint
        WHERE uid = %s
          AND username IS NOT NULL
          AND btrim(username) <> ''
        ORDER BY id DESC
        LIMIT 1;
    """
    username = db_scalar(sql, (uid,))
    if username:
        return username

    sql = """
        SELECT subject_dn
        FROM public.certificate
        WHERE client_uid = %s
        ORDER BY id DESC
        LIMIT 1;
    """
    subject_dn = db_scalar(sql, (uid,))
    cn = _extract_cn_from_subject_dn(subject_dn)
    if cn:
        return cn
    return subject_dn


def resolve_seed_plan_for_username(username: str) -> dict[str, Any]:
    u = str(username or "").strip()
    if not u:
        return {
            "username": "",
            "callsign": "",
            "seed_channels": [],
            "assignment_hash": "",
        }

    try:
        ensure_takctl_importable()

        from takctl.onboarding.service_builder import build_service
        from takctl.onboarding.voice_topology import derive_voice_topology

        svc = build_service()
        ident = svc.store.get_identity(u)

        callsign = u
        seed_channels: list[str] = []
        ctx: dict[str, Any] = {}

        if ident is not None:
            ctx = dict(getattr(ident, "ctx", {}) or {})
            derived = dict(getattr(ident, "identity", {}) or {})
            callsign = str(derived.get("callsign") or u).strip() or u

            if ctx:
                topo = derive_voice_topology(None, ctx)
                seed_channels = [
                    str(x).strip()
                    for x in (topo.get("seed_channels") or [])
                    if str(x or "").strip()
                ][:2]

        assignment_hash = stable_hash(
            {
                "username": u,
                "ctx": ctx,
                "seed_channels": seed_channels,
            }
        )

        return {
            "username": u,
            "callsign": callsign,
            "seed_channels": seed_channels,
            "assignment_hash": assignment_hash,
        }
    except Exception as e:
        log.exception("resolve_seed_plan_failed username=%s err=%s", u, e)
        return {
            "username": u,
            "callsign": u,
            "seed_channels": [],
            "assignment_hash": "error",
        }


def device_state_path(username: str, client_uid: str) -> Path:
    return DEVICE_STATE_ROOT / str(username or "").strip() / f"{str(client_uid or '').strip()}.json"


def load_device_state(username: str, client_uid: str) -> dict[str, Any]:
    p = device_state_path(username, client_uid)
    raw = read_json(p)
    if not isinstance(raw, dict):
        return {
            "username": str(username or "").strip(),
            "client_uid": str(client_uid or "").strip(),
            "hello_sent_at": None,
            "chat_groups_seeded_at": None,
            "chat_groups_seed_assignment_hash": None,
            "seed_channels": [],
        }
    raw.setdefault("username", str(username or "").strip())
    raw.setdefault("client_uid", str(client_uid or "").strip())
    raw.setdefault("hello_sent_at", None)
    raw.setdefault("chat_groups_seeded_at", None)
    raw.setdefault("chat_groups_seed_assignment_hash", None)
    raw.setdefault("seed_channels", [])
    return raw


def save_device_state(username: str, client_uid: str, state: dict[str, Any]) -> None:
    p = device_state_path(username, client_uid)
    write_json(p, state)


def list_recent_client_devices() -> List[dict[str, Any]]:
    sql = """
        SELECT
          uid,
          MIN(servertime) AS first_seen,
          MAX(servertime) AS last_seen
        FROM cot_router
        WHERE servertime >= NOW() - (%s * INTERVAL '1 minute')
          AND uid IS NOT NULL
          AND uid <> ''
          AND uid NOT LIKE 'GeoChat.%%'
          AND uid NOT LIKE 'martine:%%'
          AND uid NOT LIKE 'replay:%%'
        GROUP BY uid
        ORDER BY MAX(servertime) DESC, uid ASC
        LIMIT %s;
    """
    rows = db_rows(sql, (int(BOOTSTRAP_LOOKBACK_MINUTES), 5000))
    out: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 3:
            continue
        uid = str(row[0] or "").strip()
        if not uid:
            continue
        first_seen = row[1]
        last_seen = row[2]
        out.append(
            {
                "client_uid": uid,
                "first_seen_at": iso_z(first_seen) if isinstance(first_seen, datetime) else str(first_seen or "").strip(),
                "last_seen_at": iso_z(last_seen) if isinstance(last_seen, datetime) else str(last_seen or "").strip(),
            }
        )
    return out


def parse_chat_xml(xml_text: str):
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    detail = root.find("detail")
    if detail is None:
        return None

    uid = str(root.attrib.get("uid") or "").strip()
    chat = detail.find("__chat")
    remarks = detail.find("remarks")
    link = detail.find("link")

    if chat is None or remarks is None:
        return None

    sender_callsign = str(chat.attrib.get("senderCallsign") or "").strip()
    to_callsign = str(chat.attrib.get("chatroom") or "").strip()
    message = str(remarks.text or "").strip()
    to_uid = str(remarks.attrib.get("to") or "").strip()

    sender_uid = ""
    chatgrp = chat.find("chatgrp")
    if chatgrp is not None:
        uid0 = str(chatgrp.attrib.get("uid0") or "").strip()
        uid1 = str(chatgrp.attrib.get("uid1") or "").strip()
        uid2 = str(chatgrp.attrib.get("uid2") or "").strip()
        chat_id = str(chatgrp.attrib.get("id") or "").strip()

        if to_uid and uid1 == to_uid:
            sender_uid = uid0
        elif to_uid and uid0 == to_uid:
            sender_uid = uid1
        elif to_uid and uid2 == to_uid:
            sender_uid = uid0 or uid1
        elif chat_id and uid0 and chat_id == uid1:
            sender_uid = uid0

    if not sender_uid and link is not None:
        sender_uid = str(link.attrib.get("uid") or "").strip()

    if not to_callsign or not message:
        return None

    return {
        "uid": uid,
        "from_callsign": sender_callsign,
        "from_uid": sender_uid,
        "to_callsign": to_callsign,
        "to_uid": to_uid,
        "kind": "message",
        "message": message,
        "meta": {},
        "raw_xml": xml_text,
    }


def build_presence_xml(*, chat_uid: str, callsign: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=10))

    return (
        f'<event version="2.0" uid="{escape(chat_uid)}" type="a-f-G-U-C" how="h-e" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="32.076" ce="3.8" le="9999999.0"/>'
        f'<detail>'
        f'<contact callsign="{escape(callsign)}" endpoint="*:-1:stcp"/>'
        f'<__group name="Blue" role="Team Member"/>'
        f'<precisionlocation geopointsrc="GPS" altsrc="GPS"/>'
        f'<status battery="100"/>'
        f'<takv device="Martine" platform="ATAK-CIV" os="Linux" version="Martine/1.0"/>'
        f'<track speed="0.0" course="0.0"/>'
        f'<uid Droid="{escape(callsign)}"/>'
        f'</detail>'
        f'</event>'
    )


def build_atak_chat_xml(
    *,
    chat_uid: str,
    callsign: str,
    to_uid: str,
    to_callsign: str,
    message: str,
    parent: str = "RootContactGroup",
    sender_callsign_override: str = "",
) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    room = str(to_callsign or to_uid or ALL_CHAT_ROOMS).strip() or ALL_CHAT_ROOMS
    target_uid = str(to_uid or room).strip() or room
    uid = f"GeoChat.{chat_uid}.{target_uid}.{message_id}"
    remarks_source = f"BAO.F.ATAK.{chat_uid}"
    visible_callsign = str(sender_callsign_override or callsign).strip() or callsign

    marti_dest_xml = ""
    if parent == "RootContactGroup":
        dest_callsign = str(to_callsign or "").strip()
        if dest_callsign and dest_callsign != ALL_CHAT_ROOMS:
            marti_dest_xml = f'<marti><dest callsign="{escape(dest_callsign)}"/></marti>'

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="{escape(parent)}" groupOwner="false" messageId="{escape(message_id)}" '
        f'chatroom="{escape(room)}" id="{escape(target_uid)}" senderCallsign="{escape(visible_callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(target_uid)}" id="{escape(target_uid)}"/>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="{escape(remarks_source)}" to="{escape(target_uid)}" time="{time_s}">{escape(message)}</remarks>'
        f'{marti_dest_xml}'
        f'</detail>'
        f'</event>'
    )

def build_group_contacts_update_xml(
    *,
    chat_uid: str,
    callsign: str,
    recipient_uid: str,
    recipient_callsign: str,
    group_name: str,
) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    group_uid = stable_group_id(group_name, recipient_uid, chat_uid)

    return (
        f'<event version="2.0" uid="GeoChat.{escape(chat_uid)}.{escape(group_uid)}.{escape(message_id)}" '
        f'type="b-t-f" how="h-g-i-g-o" time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="UserGroups" groupOwner="true" messageId="{escape(message_id)}" '
        f'chatroom="{escape(group_name)}" id="{escape(group_uid)}" senderCallsign="{escape(callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(recipient_uid)}" id="{escape(group_uid)}"/>'
        f'<hierarchy>'
        f'<group uid="UserGroups" name="Groups">'
        f'<group uid="{escape(group_uid)}" name="{escape(group_name)}">'
        f'<contact uid="{escape(recipient_uid)}" name="{escape(recipient_callsign)}"/>'
        f'<contact uid="{escape(chat_uid)}" name="{escape(callsign)}"/>'
        f'</group>'
        f'</group>'
        f'</hierarchy>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="BAO.F.ATAK.{escape(chat_uid)}" time="{time_s}">[UPDATED CONTACTS]</remarks>'
        f'<marti><dest callsign="{escape(recipient_callsign)}"/></marti>'
        f'</detail>'
        f'</event>'
    )


def build_group_seed_message_xml(
    *,
    chat_uid: str,
    callsign: str,
    recipient_uid: str,
    recipient_callsign: str,
    group_name: str,
    message: str,
) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    group_uid = stable_group_id(group_name, recipient_uid, chat_uid)

    return (
        f'<event version="2.0" uid="GeoChat.{escape(chat_uid)}.{escape(group_uid)}.{escape(message_id)}" '
        f'type="b-t-f" how="h-g-i-g-o" time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="UserGroups" groupOwner="false" messageId="{escape(message_id)}" '
        f'chatroom="{escape(group_name)}" id="{escape(group_uid)}" senderCallsign="{escape(callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(recipient_uid)}" id="{escape(group_uid)}"/>'
        f'<hierarchy>'
        f'<group uid="UserGroups" name="Groups">'
        f'<group uid="{escape(group_uid)}" name="{escape(group_name)}">'
        f'<contact uid="{escape(recipient_uid)}" name="{escape(recipient_callsign)}"/>'
        f'<contact uid="{escape(chat_uid)}" name="{escape(callsign)}"/>'
        f'</group>'
        f'</group>'
        f'</hierarchy>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="BAO.F.ATAK.{escape(chat_uid)}" time="{time_s}">{escape(message)}</remarks>'
        f'<marti><dest callsign="{escape(recipient_callsign)}"/></marti>'
        f'</detail>'
        f'</event>'
    )


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=CA_PEM)
    _load_client_chain(ctx)
    return ctx


def send_event(sock: ssl.SSLSocket, xml_text: str) -> None:
    sock.sendall(xml_text.encode("utf-8"))


def recv_xml(sock: ssl.SSLSocket, timeout: float = 1.0) -> str | None:
    sock.settimeout(timeout)
    try:
        data = sock.recv(1024 * 1024)
    except socket.timeout:
        return None
    if not data:
        raise ConnectionError("socket closed by peer")
    return data.decode("utf-8", errors="replace")


def maybe_process_recent_devices(sock: ssl.SSLSocket, cfg) -> None:
    now_dt = datetime.now(timezone.utc)
    rows = list_recent_client_devices()

    for row in rows:
        client_uid = str(row.get("client_uid") or "").strip()
        if not client_uid:
            continue
        if client_uid == str(cfg.chat_uid or "").strip():
            continue

        username = resolve_username_for_client_uid(client_uid)
        if not username:
            continue

        first_seen_at = parse_dt(row.get("first_seen_at"))
        if first_seen_at is None:
            continue

        age_sec = int((now_dt - first_seen_at).total_seconds())
        if age_sec < BOOTSTRAP_DELAY_SEC:
            continue

        plan = resolve_seed_plan_for_username(username)
        recipient_callsign = str(plan.get("callsign") or username).strip() or username
        seed_channels = [
            str(x).strip()
            for x in (plan.get("seed_channels") or [])
            if str(x or "").strip()
        ][:2]
        assignment_hash = str(plan.get("assignment_hash") or "").strip()

        state = load_device_state(username, client_uid)
        changed = False

        if not state.get("hello_sent_at"):
            hello_msg = (
                f"Hej {recipient_callsign}. Jag är {cfg.callsign}. "
                "Du kan ställa frågor till mig här i chatten."
            )
            send_event(
                sock,
                build_atak_chat_xml(
                    chat_uid=cfg.chat_uid,
                    callsign=cfg.callsign,
                    to_uid=client_uid,
                    to_callsign=recipient_callsign,
                    message=hello_msg,
                    parent="RootContactGroup",
                ),
            )
            state["hello_sent_at"] = iso_z(now_dt)
            changed = True
            log.info(
                "bootstrap_hello_sent username=%s client_uid=%s recipient=%s",
                username,
                client_uid,
                recipient_callsign,
            )
            time.sleep(0.10)

        prev_hash = str(state.get("chat_groups_seed_assignment_hash") or "").strip()
        if seed_channels and assignment_hash and assignment_hash != prev_hash:
            for group_name in seed_channels:
                send_event(
                    sock,
                    build_group_contacts_update_xml(
                        chat_uid=cfg.chat_uid,
                        callsign=cfg.callsign,
                        recipient_uid=client_uid,
                        recipient_callsign=recipient_callsign,
                        group_name=group_name,
                    ),
                )
                time.sleep(0.10)

                send_event(
                    sock,
                    build_group_seed_message_xml(
                        chat_uid=cfg.chat_uid,
                        callsign=cfg.callsign,
                        recipient_uid=client_uid,
                        recipient_callsign=recipient_callsign,
                        group_name=group_name,
                        message=f"Martine seeding group {group_name}",
                    ),
                )
                log.info(
                    "bootstrap_group_seed_sent username=%s client_uid=%s group=%s",
                    username,
                    client_uid,
                    group_name,
                )
                time.sleep(0.10)

            state["chat_groups_seeded_at"] = iso_z(now_dt)
            state["chat_groups_seed_assignment_hash"] = assignment_hash
            state["seed_channels"] = list(seed_channels)
            changed = True

        if changed:
            save_device_state(username, client_uid, state)


def _is_message_for_martine(msg: dict[str, Any], cfg) -> bool:
    to_uid = str(msg.get("to_uid") or "").strip()
    to_callsign = str(msg.get("to_callsign") or "").strip()
    my_uid = str(cfg.chat_uid or "").strip()
    my_callsign = str(cfg.callsign or "").strip()

    if to_uid and my_uid and to_uid == my_uid:
        return True
    if to_callsign and my_callsign and to_callsign == my_callsign:
        return True
    return False


def handle_one_message(sock: ssl.SSLSocket, cfg, text: str) -> None:
    from martine.agent.simple_agent import run_once

    log.info("incoming_xml bytes=%s", len(text.encode("utf-8", errors="ignore")))

    msg = parse_chat_xml(text)
    if not msg:
        log.info("incoming_xml ignored=parse_chat_xml_none")
        return

    if not _is_message_for_martine(msg, cfg):
        log.info(
            "incoming_chat ignored wrong_recipient to_callsign=%s expected=%s from_callsign=%s uid=%s",
            msg.get("to_callsign"),
            cfg.callsign,
            msg.get("from_callsign"),
            msg.get("uid"),
        )
        return

    question = str(msg.get("message") or "").strip()
    if not question:
        log.info(
            "incoming_chat ignored empty_question from_callsign=%s from_uid=%s",
            msg.get("from_callsign"),
            msg.get("from_uid"),
        )
        return

    log.info(
        "incoming_chat accepted from_callsign=%s from_uid=%s to_callsign=%s question=%r",
        msg.get("from_callsign"),
        msg.get("from_uid"),
        msg.get("to_callsign"),
        question[:500],
    )

    result = run_once(
        question,
        sender_uid=str(msg.get("from_uid") or "").strip(),
        sender_callsign=str(msg.get("from_callsign") or "").strip(),
    )
    answer = str(result.get("answer") or "").strip()

    log.info(
        "agent_result ok=%s run_id=%s error=%s answer_preview=%r",
        result.get("ok"),
        result.get("run_id"),
        result.get("error"),
        answer[:500],
    )

    if not answer:
        answer = f"Jag kunde inte svara just nu. Fel: {result.get('error') or 'okänt fel'}"

    to_uid = str(msg.get("from_uid") or "").strip()
    to_callsign = str(msg.get("from_callsign") or "").strip()

    send_event(
        sock,
        build_atak_chat_xml(
            chat_uid=cfg.chat_uid,
            callsign=cfg.callsign,
            to_uid=to_uid,
            to_callsign=to_callsign,
            message=answer,
            parent="RootContactGroup",
        ),
    )
    log.info(
        "reply_sent to_callsign=%s to_uid=%s run_id=%s",
        to_callsign,
        to_uid,
        result.get("run_id"),
    )


def session_loop() -> None:
    from martine.config import load_config

    setup_martine_logging()
    ensure_state_dirs()
    cfg = load_config()
    ctx = ssl_context()

    with socket.create_connection((HOST, PORT), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname="tak-hv-sandbox.se") as sock:
            info = {
                "ok": True,
                "mode": "cot_tls_client",
                "host": HOST,
                "port": PORT,
                "callsign": cfg.callsign,
                "chat_uid": cfg.chat_uid,
                "tls_version": sock.version(),
                "cipher": sock.cipher(),
            }
            print(info, flush=True)
            log.info("cot_session_connected %s", info)

            send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
            send_event(
                sock,
                build_atak_chat_xml(
                    chat_uid=cfg.chat_uid,
                    callsign=cfg.callsign,
                    to_uid=ALL_CHAT_ROOMS,
                    to_callsign=ALL_CHAT_ROOMS,
                    message="Martine online. Ställ frågor till mig i chatten.",
                    parent="RootContactGroup",
                ),
            )

            last_presence = time.time()
            last_bootstrap_poll = 0.0

            while True:
                now = time.time()

                if now - last_presence >= float(cfg.presence_interval_sec):
                    send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
                    last_presence = now

                if now - last_bootstrap_poll >= float(BOOTSTRAP_POLL_INTERVAL_SEC):
                    maybe_process_recent_devices(sock, cfg)
                    last_bootstrap_poll = now

                text = recv_xml(sock, timeout=1.0)
                if text is None:
                    continue
                handle_one_message(sock, cfg, text)


def main() -> None:
    backoff = 2.0
    while True:
        try:
            session_loop()
            backoff = 2.0
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print({"ok": False, "where": "cot_tls_client", "error": str(e)}, flush=True)
            log.exception("cot_tls_client_loop_failed error=%s", e)
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)


if __name__ == "__main__":
    main()
