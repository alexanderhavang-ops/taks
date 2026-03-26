from __future__ import annotations

import socket
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from martine.agent.simple_agent import run_once
from martine.config import load_config


HOST = "127.0.0.1"
PORT = 8089

IDENTITY_DIR = "/opt/tak/tools/martine/runtime/identity"
CERT_PEM = f"{IDENTITY_DIR}/client.pem"
KEY_PEM = f"{IDENTITY_DIR}/client.key"
CA_PEM = f"{IDENTITY_DIR}/ca.pem"
KEY_PASSWORD = "cert-pass-46-pass"

ALL_CHAT_ROOMS = "All Chat Rooms"


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def build_atak_chat_xml(*, chat_uid: str, callsign: str, to_uid: str, to_callsign: str, message: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    room = to_callsign or to_uid or ALL_CHAT_ROOMS
    target_uid = to_uid or room
    uid = f"GeoChat.{chat_uid}.{target_uid}.{message_id}"
    remarks_source = f"BAO.F.ATAK.{chat_uid}"

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="RootContactGroup" groupOwner="false" messageId="{escape(message_id)}" '
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


def handle_one_message(sock: ssl.SSLSocket, cfg, text: str) -> None:
    msg = parse_chat_xml(text)
    if not msg:
        return
    if str(msg.get("to_callsign") or "") != cfg.callsign:
        return

    question = str(msg.get("message") or "").strip()
    if not question:
        return

    result = run_once(question)
    answer = str(result.get("answer") or "").strip()
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
        ),
    )


def session_loop() -> None:
    cfg = load_config()
    ctx = ssl_context()

    with socket.create_connection((HOST, PORT), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname="tak-hv-sandbox.se") as sock:
            print(
                {
                    "ok": True,
                    "mode": "cot_tls_client",
                    "host": HOST,
                    "port": PORT,
                    "callsign": cfg.callsign,
                    "chat_uid": cfg.chat_uid,
                    "tls_version": sock.version(),
                    "cipher": sock.cipher(),
                },
                flush=True,
            )

            send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
            send_event(
                sock,
                build_atak_chat_xml(
                    chat_uid=cfg.chat_uid,
                    callsign=cfg.callsign,
                    to_uid=ALL_CHAT_ROOMS,
                    to_callsign=ALL_CHAT_ROOMS,
                    message="Martine online. Ställ frågor till mig i chatten.",
                ),
            )

            last_presence = time.time()

            while True:
                now = time.time()
                if now - last_presence >= float(cfg.presence_interval_sec):
                    send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
                    last_presence = now

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
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 30.0)


if __name__ == "__main__":
    main()
