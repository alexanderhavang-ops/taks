from __future__ import annotations

import hashlib
import json
import os
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
KEY_PASSWORD = "cert-pass-46-pass"

ALL_CHAT_ROOMS = "All Chat Rooms"

BOOTSTRAP_DELAY_SEC = 180
BOOTSTRAP_POLL_INTERVAL_SEC = 30
BOOTSTRAP_LOOKBACK_MINUTES = 240

TAKS_ONBOARDING_ROOT = Path("/opt/tak/takctl-state/onboarding")
DEVICE_STATE_ROOT = TAKS_ONBOARDING_ROOT / "devices"

TAKCTL_CFG_PATHS = (
    Path("/opt/tak/tools/takctl/takctl.conf"),
    Path("/opt/tak/tools/takctl/secrets.conf"),
    Path("/opt/taks/takctl/takctl.conf"),
    Path("/opt/taks/takctl/secrets.conf"),
)


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


def _iso_or_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    return str(value).strip()


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
    ):
        if p not in sys.path and Path(p).exists():
            sys.path.append(p)


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _strip_quotes(v: str) -> str:
    s = str(v or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


def _read_simple_kv(paths: tuple[Path, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        try:
            if not p.exists():
                continue
            for raw in p.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = str(k or "").strip()
                if not key:
                    continue
                out[key] = _strip_quotes(v)
        except Exception:
            continue
    return out


def _pg_driver():
    try:
        import psycopg2  # type: ignore

        return "psycopg2", psycopg2
    except Exception:
        pass

    try:
        import psycopg  # type: ignore

        return "psycopg", psycopg
    except Exception as e:
        raise RuntimeError("Neither psycopg2 nor psycopg is available") from e


def _candidate_fingerprint(d: dict[str, Any]) -> str:
    safe = {k: ("***" if "pass" in k.lower() else v) for k, v in d.items()}
    return json.dumps(safe, sort_keys=True, default=str)


def _build_db_candidates() -> list[dict[str, Any]]:
    cfg = _read_simple_kv(TAKCTL_CFG_PATHS)

    dbname = (
        str(
            cfg.get("db_name")
            or cfg.get("database")
            or os.environ.get("PGDATABASE")
            or "cot"
        ).strip()
        or "cot"
    )
    host_cfg = str(cfg.get("db_host") or os.environ.get("PGHOST") or "").strip()
    port_raw = str(cfg.get("db_port") or os.environ.get("PGPORT") or "5432").strip()
    try:
        port_cfg = int(port_raw)
    except Exception:
        port_cfg = 5432

    dsn = str(
        cfg.get("database_url")
        or cfg.get("db_url")
        or cfg.get("postgres_url")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("PGURL")
        or ""
    ).strip()

    explicit_user = str(
        cfg.get("db_user")
        or cfg.get("pg_user")
        or cfg.get("postgres_user")
        or os.environ.get("PGUSER")
        or ""
    ).strip()

    explicit_password = str(
        cfg.get("db_password")
        or cfg.get("pg_password")
        or cfg.get("postgres_password")
        or cfg.get("password")
        or os.environ.get("PGPASSWORD")
        or ""
    ).strip()

    fallback_users: list[str] = []
    for u in (
        explicit_user,
        os.environ.get("USER"),
        os.environ.get("LOGNAME"),
        "tak",
        cfg.get("sudo_user"),
        "postgres",
    ):
        s = str(u or "").strip()
        if s and s not in fallback_users:
            fallback_users.append(s)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(candidate: dict[str, Any]) -> None:
        fp = _candidate_fingerprint(candidate)
        if fp in seen:
            return
        seen.add(fp)
        candidates.append(candidate)

    if dsn:
        add({"dsn": dsn})

    if host_cfg or explicit_user or explicit_password:
        cand: dict[str, Any] = {"dbname": dbname, "port": port_cfg}
        if host_cfg:
            cand["host"] = host_cfg
        if explicit_user:
            cand["user"] = explicit_user
        if explicit_password:
            cand["password"] = explicit_password
        add(cand)

    if explicit_user:
        cand = {"dbname": dbname, "host": "/var/run/postgresql", "user": explicit_user}
        if explicit_password:
            cand["password"] = explicit_password
        add(cand)

    if host_cfg:
        add({"dbname": dbname, "host": host_cfg, "port": port_cfg})

    for user in fallback_users:
        add({"dbname": dbname, "host": "/var/run/postgresql", "user": user})
        add({"dbname": dbname, "user": user})

    add({"dbname": dbname, "host": "/var/run/postgresql"})
    add({"dbname": dbname})

    return candidates


def _connect_pg(driver_name: str, driver: Any, candidate: dict[str, Any]):
    kwargs = dict(candidate)
    if "dsn" in kwargs and len(kwargs) == 1:
        conn = driver.connect(kwargs["dsn"])
    else:
        conn = driver.connect(**kwargs)
    try:
        conn.autocommit = True
    except Exception:
        pass
    return conn


def db_rows(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    try:
        driver_name, driver = _pg_driver()
    except Exception as e:
        log.warning("db_driver_unavailable err=%s", e)
        return []

    errors: list[str] = []
    for candidate in _build_db_candidates():
        try:
            conn = _connect_pg(driver_name, driver, candidate)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall() or []
                    return list(rows)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            fp = _candidate_fingerprint(candidate)
            errors.append(f"{fp}: {e.__class__.__name__}: {e}")

    if errors:
        log.warning("db_rows_failed sql=%r err=%s", sql[:500], " | ".join(errors[:3])[:1500])
    return []


def db_scalar(sql: str, params: tuple[Any, ...] = ()) -> str:
    rows = db_rows(sql, params)
    if not rows:
        return ""
    row0 = rows[0]
    if not row0:
        return ""
    return str(row0[0] or "").strip()


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
        out.append(
            {
                "client_uid": uid,
                "first_seen_at": _iso_or_text(row[1]),
                "last_seen_at": _iso_or_text(row[2]),
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
        chat_id = str(chatgrp.attrib.get("id") or "").strip()
        if to_uid and uid1 == to_uid:
            sender_uid = uid0
        elif to_uid and uid0 == to_uid:
            sender_uid = uid1
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
) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    room = str(to_callsign or to_uid or ALL_CHAT_ROOMS).strip() or ALL_CHAT_ROOMS
    target_uid = str(to_uid or room).strip() or room
    uid = f"GeoChat.{chat_uid}.{target_uid}.{message_id}"
    remarks_source = f"BAO.F.ATAK.{chat_uid}"

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="{escape(parent)}" groupOwner="false" messageId="{escape(message_id)}" '
        f'chatroom="{escape(room)}" id="{escape(target_uid)}" senderCallsign="{escape(callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(target_uid)}" id="{escape(target_uid)}"/>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="{escape(remarks_source)}" to="{escape(target_uid)}" time="{time_s}">{escape(message)}</remarks>'
        f'</detail>'
        f'</event>'
    )


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=CA_PEM)
    ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM, password=KEY_PASSWORD)
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
                msg = f"Martine seeding group {group_name}"
                send_event(
                    sock,
                    build_atak_chat_xml(
                        chat_uid=cfg.chat_uid,
                        callsign=cfg.callsign,
                        to_uid=client_uid,
                        to_callsign=group_name,
                        message=msg,
                        parent="UserGroups",
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


def handle_one_message(sock: ssl.SSLSocket, cfg, text: str) -> None:
    from martine.agent.simple_agent import run_once

    log.info("incoming_xml bytes=%s", len(text.encode("utf-8", errors="ignore")))

    msg = parse_chat_xml(text)
    if not msg:
        log.info("incoming_xml ignored=parse_chat_xml_none")
        return
    if str(msg.get("to_callsign") or "") != cfg.callsign:
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
