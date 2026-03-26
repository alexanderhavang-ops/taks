from __future__ import annotations

import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from martine.agent.simple_agent import run_once
from martine.config import load_config


ALL_CHAT_ROOMS = "All Chat Rooms"


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_chat_xml(xml_text: str) -> Optional[Dict[str, Any]]:
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

    if chat is not None and remarks is not None:
        sender = str(chat.attrib.get("senderCallsign") or "").strip()
        to = str(chat.attrib.get("chatroom") or chat.attrib.get("id") or "").strip()
        msg = str(remarks.text or "").strip()
        if to and msg:
            return {
                "uid": uid,
                "from": sender,
                "to": to,
                "kind": "message",
                "message": msg,
                "meta": {},
                "raw_xml": xml_text,
            }

    return None


def build_presence_xml(*, chat_uid: str, callsign: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=10))

    # Mimic ATAK handset presence much more closely.
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


def build_atak_chat_xml(*, chat_uid: str, callsign: str, to: str, message: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    uid = f"GeoChat.{chat_uid}.{to}.{message_id}"
    remarks_source = f"BAO.F.ATAK.{chat_uid}"

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="RootContactGroup" groupOwner="false" messageId="{escape(message_id)}" '
        f'chatroom="{escape(to)}" id="{escape(to)}" senderCallsign="{escape(callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(to)}" id="{escape(to)}"/>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="{escape(remarks_source)}" to="{escape(to)}" time="{time_s}">{escape(message)}</remarks>'
        f'</detail>'
        f'</event>'
    )


def send_udp(sock: socket.socket, xml_text: str, host: str, port: int) -> None:
    sock.sendto(xml_text.encode("utf-8"), (host, port))


def run_forever() -> None:
    cfg = load_config()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((cfg.cot_listen_host, cfg.cot_listen_port))
    sock.settimeout(1.0)

    print({
        "ok": True,
        "callsign": cfg.callsign,
        "chat_uid": cfg.chat_uid,
        "listen_host": cfg.cot_listen_host,
        "listen_port": cfg.cot_listen_port,
        "udp_host": cfg.cot_udp_host,
        "udp_port": cfg.cot_udp_port,
        "presence_interval_sec": cfg.presence_interval_sec,
        "config": cfg.loaded_from,
    }, flush=True)

    send_udp(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign), cfg.cot_udp_host, cfg.cot_udp_port)
    send_udp(
        sock,
        build_atak_chat_xml(
            chat_uid=cfg.chat_uid,
            callsign=cfg.callsign,
            to=ALL_CHAT_ROOMS,
            message="Martine online. Ställ frågor till mig i chatten.",
        ),
        cfg.cot_udp_host,
        cfg.cot_udp_port,
    )

    last_presence = time.time()

    while True:
        now = time.time()
        if now - last_presence >= float(cfg.presence_interval_sec):
            send_udp(
                sock,
                build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign),
                cfg.cot_udp_host,
                cfg.cot_udp_port,
            )
            last_presence = now

        try:
            data, _addr = sock.recvfrom(1024 * 1024)
        except socket.timeout:
            continue

        text = data.decode("utf-8", errors="replace")
        msg = parse_chat_xml(text)
        if not msg:
            continue
        if str(msg.get("to") or "") != cfg.callsign:
            continue

        question = str(msg.get("message") or "").strip()
        if not question:
            continue

        result = run_once(question)
        answer = str(result.get("answer") or "").strip()
        if not answer:
            answer = f"Jag kunde inte svara just nu. Fel: {result.get('error') or 'okänt fel'}"

        send_udp(
            sock,
            build_atak_chat_xml(
                chat_uid=cfg.chat_uid,
                callsign=cfg.callsign,
                to=str(msg.get("from") or ALL_CHAT_ROOMS),
                message=answer,
            ),
            cfg.cot_udp_host,
            cfg.cot_udp_port,
        )
        time.sleep(0.05)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
