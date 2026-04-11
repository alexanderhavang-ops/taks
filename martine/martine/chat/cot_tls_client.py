from __future__ import annotations

import hashlib
import json
import socket
import ssl
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from martine.agent.simple_agent import run_once
from martine.config import load_config
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


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(value: str | None) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
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
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cot_runtime_dir() -> Path:
    root = martine_state_dir()
    d = root / "cot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bootstrap_state_path() -> Path:
    return cot_runtime_dir() / "device_bootstrap_state.json"


def load_bootstrap_state() -> dict[str, Any]:
    raw = read_json(bootstrap_state_path())
    if not isinstance(raw, dict):
        return {"version": 1, "devices": {}}
    devices = raw.get("devices")
    if not isinstance(devices, dict):
        raw["devices"] = {}
    raw.setdefault("version", 1)
    return raw


def save_bootstrap_state(state: dict[str, Any]) -> None:
    write_json(bootstrap_state_path(), state)


def make_state_key(username: str, client_uid: str) -> str:
    u = str(username or "").strip() or "?"
    c = str(client_uid or "").strip()
    return f"{u}:{c}"


def find_state_record(
    state: dict[str, Any],
    *,
    client_uid: str,
    username: str = "",
) -> Tuple[Optional[str], Optional[dict[str, Any]]]:
    devices = state.get("devices") or {}
    if username:
        k = make_state_key(username, client_uid)
        rec = devices.get(k)
        if isinstance(rec, dict):
            return k, rec
    for k, rec in devices.items():
        if not isinstance(rec, dict):
            continue
        if str(rec.get("client_uid") or "").strip() == client_uid:
            return str(k), rec
    return None, None


def ensure_state_record(
    state: dict[str, Any],
    *,
    client_uid: str,
    username: str,
    observed_callsign: str,
    now_dt: datetime,
) -> tuple[str, dict[str, Any], bool]:
    devices = state.setdefault("devices", {})
    old_key, rec = find_state_record(state, client_uid=client_uid, username=username)
    changed = False

    if rec is None:
        key = make_state_key(username, client_uid)
        rec = {
            "username": str(username or "").strip() or None,
            "client_uid": client_uid,
            "first_seen_at": iso_z(now_dt),
            "last_seen_at": iso_z(now_dt),
            "observed_callsign": observed_callsign or None,
            "hello_sent_at": None,
            "group_seed_sent_at": None,
            "group_seed_assignment_hash": None,
            "seed_channels": [],
        }
        devices[key] = rec
        return key, rec, True

    key = old_key or make_state_key(username, client_uid)

    want_username = str(username or "").strip()
    have_username = str(rec.get("username") or "").strip()
    if want_username and want_username != have_username:
        rec["username"] = want_username
        changed = True

    new_key = make_state_key(str(rec.get("username") or "").strip(), client_uid)
    if new_key != key:
        if key in devices:
            del devices[key]
        devices[new_key] = rec
        key = new_key
        changed = True

    rec["last_seen_at"] = iso_z(now_dt)
    changed = True

    if not rec.get("first_seen_at"):
        rec["first_seen_at"] = iso_z(now_dt)
        changed = True

    if observed_callsign and str(rec.get("observed_callsign") or "").strip() != observed_callsign:
        rec["observed_callsign"] = observed_callsign
        changed = True

    return key, rec, changed


def stable_hash(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def escape_sql_literal(value: str) -> str:
    return str(value or "").replace("'", "''")


def psql_scalar(sql: str) -> str:
    cmd = [
        "sudo", "-u", "postgres",
        "psql", "-d", "cot",
        "-P", "pager=off",
        "-A", "-t",
        "-c", sql,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if err:
            log.warning("psql_scalar_failed err=%s sql=%r", err[:500], sql[:500])
        return ""
    for line in proc.stdout.splitlines():
        s = str(line or "").strip()
        if s:
            return s
    return ""


def resolve_username_for_client_uid(client_uid: str) -> str:
    uid = str(client_uid or "").strip()
    if not uid:
        return ""
    sql = (
        "SELECT subject_dn "
        "FROM public.certificate "
        f"WHERE client_uid = '{escape_sql_literal(uid)}' "
        "ORDER BY id DESC "
        "LIMIT 1;"
    )
    return psql_scalar(sql)


def resolve_seed_plan_for_username(username: str) -> dict[str, Any]:
    u = str(username or "").strip()
    if not u:
        return {"username": "", "callsign": "", "seed_channels": [], "assignment_hash": ""}

    try:
        from takctl.onboarding.service_builder import build_service
        from takctl.onboarding.voice_topology import derive_voice_topology

        svc = build_service()
        ident = svc.store.get_identity(u)
        if ident is None:
            return {"username": u, "callsign": u, "seed_channels": [], "assignment_hash": "no_identity"}

        ctx = dict(getattr(ident, "ctx", {}) or {})
        derived = dict(getattr(ident, "identity", {}) or {})
        callsign = str(derived.get("callsign") or u).strip()

        seed_channels: list[str] = []
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
        return {"username": u, "callsign": u, "seed_channels": [], "assignment_hash": "error"}


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


def parse_observed_endpoint(xml_text: str, *, own_chat_uid: str, own_callsign: str) -> Optional[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None

    uid = str(root.attrib.get("uid") or "").strip()
    if not uid:
        return None
    if uid == str(own_chat_uid or "").strip():
        return None
    if uid.startswith("GeoChat.") or uid.startswith("martine:"):
        return None

    detail = root.find("detail")
    if detail is None:
        return None

    contact = detail.find("contact")
    callsign = ""
    if contact is not None:
        callsign = str(contact.attrib.get("callsign") or "").strip()

    if callsign == str(own_callsign or "").strip():
        return None
    if callsign == f"{str(own_callsign or '').strip()}-CHAT":
        return None

    return {
        "client_uid": uid,
        "observed_callsign": callsign,
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


def maybe_record_seen_device(xml_text: str, cfg) -> None:
    obs = parse_observed_endpoint(
        xml_text,
        own_chat_uid=str(cfg.chat_uid),
        own_callsign=str(cfg.callsign),
    )
    if not obs:
        return

    client_uid = str(obs.get("client_uid") or "").strip()
    observed_callsign = str(obs.get("observed_callsign") or "").strip()
    if not client_uid:
        return

    username = resolve_username_for_client_uid(client_uid)
    now_dt = datetime.now(timezone.utc)

    state = load_bootstrap_state()
    key, rec, changed = ensure_state_record(
        state,
        client_uid=client_uid,
        username=username,
        observed_callsign=observed_callsign,
        now_dt=now_dt,
    )
    if changed:
        save_bootstrap_state(state)
        log.info(
            "bootstrap_seen key=%s username=%s client_uid=%s observed_callsign=%s",
            key,
            rec.get("username"),
            client_uid,
            observed_callsign,
        )


def maybe_send_bootstrap_messages(sock: ssl.SSLSocket, cfg) -> None:
    state = load_bootstrap_state()
    devices = state.get("devices") or {}
    now_dt = datetime.now(timezone.utc)
    changed = False

    for key in sorted(list(devices.keys())):
        rec = devices.get(key)
        if not isinstance(rec, dict):
            continue

        client_uid = str(rec.get("client_uid") or "").strip()
        username = str(rec.get("username") or "").strip()
        observed_callsign = str(rec.get("observed_callsign") or "").strip()

        if not client_uid:
            continue
        if client_uid == str(cfg.chat_uid or "").strip():
            continue

        if not username:
            username = resolve_username_for_client_uid(client_uid)
            if username:
                rec["username"] = username
                new_key = make_state_key(username, client_uid)
                if new_key != key:
                    del devices[key]
                    devices[new_key] = rec
                    key = new_key
                changed = True

        if not username:
            continue

        first_seen_at = parse_iso_z(str(rec.get("first_seen_at") or ""))
        if first_seen_at is None:
            rec["first_seen_at"] = iso_z(now_dt)
            changed = True
            continue

        age_sec = int((now_dt - first_seen_at).total_seconds())
        if age_sec < BOOTSTRAP_DELAY_SEC:
            continue

        direct_to_callsign = observed_callsign or username

        if not rec.get("hello_sent_at"):
            hello_msg = (
                f"Hej {direct_to_callsign}. Jag är {cfg.callsign}. "
                "Du kan ställa frågor till mig här i chatten."
            )
            send_event(
                sock,
                build_atak_chat_xml(
                    chat_uid=cfg.chat_uid,
                    callsign=cfg.callsign,
                    to_uid=client_uid,
                    to_callsign=direct_to_callsign,
                    message=hello_msg,
                    parent="RootContactGroup",
                ),
            )
            rec["hello_sent_at"] = iso_z(now_dt)
            changed = True
            log.info(
                "bootstrap_hello_sent username=%s client_uid=%s to_callsign=%s",
                username,
                client_uid,
                direct_to_callsign,
            )
            time.sleep(0.10)

        plan = resolve_seed_plan_for_username(username)
        seed_channels = [str(x).strip() for x in (plan.get("seed_channels") or []) if str(x or "").strip()][:2]
        assignment_hash = str(plan.get("assignment_hash") or "").strip()

        if rec.get("seed_channels") != seed_channels:
            rec["seed_channels"] = seed_channels
            changed = True

        last_seed_hash = str(rec.get("group_seed_assignment_hash") or "").strip()
        need_seed = bool(seed_channels) and assignment_hash and assignment_hash != last_seed_hash

        if need_seed:
            for group_name in seed_channels:
                msg = f"Gruppchat {group_name} är nu aktiv."
                send_event(
                    sock,
                    build_atak_chat_xml(
                        chat_uid=cfg.chat_uid,
                        callsign=cfg.callsign,
                        to_uid=group_name,
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

            rec["group_seed_sent_at"] = iso_z(now_dt)
            rec["group_seed_assignment_hash"] = assignment_hash
            changed = True

    if changed:
        save_bootstrap_state(state)


def handle_one_message(sock: ssl.SSLSocket, cfg, text: str) -> None:
    log.info("incoming_xml bytes=%s", len(text.encode("utf-8", errors="ignore")))

    maybe_record_seen_device(text, cfg)

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

            while True:
                now = time.time()
                if now - last_presence >= float(cfg.presence_interval_sec):
                    send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
                    last_presence = now

                maybe_send_bootstrap_messages(sock, cfg)

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
