from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from replay_paths import agent_dir, ensure_runtime_dirs

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6969


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def overwrite_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_ms_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def stable_msg_id(msg: Dict[str, Any]) -> str:
    base = json.dumps(
        {
            "from": msg.get("from"),
            "to": msg.get("to"),
            "kind": msg.get("kind"),
            "sim_time_s": msg.get("sim_time_s"),
            "message": msg.get("message"),
            "meta": msg.get("meta") or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "replay-chat:" + base))


def make_uid(msg: Dict[str, Any]) -> str:
    frm = str(msg.get("from") or "UNKNOWN")
    to = str(msg.get("to") or "UNKNOWN")
    msg_id = stable_msg_id(msg)
    return f"GeoChat.REPLAY-{frm}.{to}.{msg_id}"


def build_chat_cot(msg: Dict[str, Any], now_dt: datetime) -> str:
    uid = str(msg.get("uid") or make_uid(msg))
    frm = str(msg.get("from") or "")
    to = str(msg.get("to") or "")
    message = str(msg.get("message") or "")
    msg_id = stable_msg_id(msg)

    time_s = iso_z(now_dt)
    time_ms = iso_ms_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))

    sender_uid = f"REPLAY-{frm}"
    remarks = escape(message)

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.422000" lon="13.918000" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="RootContactGroup" groupOwner="false" '
        f'messageId="{escape(msg_id)}" chatroom="{escape(to)}" id="{escape(to)}" '
        f'senderCallsign="{escape(frm)}">'
        f'<chatgrp uid0="{escape(sender_uid)}" uid1="{escape(to)}" id="{escape(to)}"/>'
        f'</__chat>'
        f'<link uid="{escape(sender_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(sender_uid)}"/>'
        f'<remarks source="{escape(sender_uid)}" to="{escape(to)}" time="{time_ms}">{remarks}</remarks>'
        f'</detail>'
        f'</event>'
    )


def send_udp(xml_text: str, host: str, port: int) -> None:
    payload = xml_text.encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload, (host, port))
    finally:
        sock.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-agent", required=True)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()

    ensure_runtime_dirs()

    d = agent_dir(args.from_agent)
    outbox_path = d / "outbox.jsonl"
    trace_path = d / "emit_trace.json"

    msgs = read_jsonl(outbox_path)
    if not msgs:
        write_json(trace_path, [])
        print("sent=0")
        return

    now_dt = datetime.now(timezone.utc)
    trace: List[Dict[str, Any]] = []
    remaining: List[Dict[str, Any]] = []
    sent = 0

    for idx, msg in enumerate(msgs, start=1):
        uid = str(msg.get("uid") or make_uid(msg))
        msg["uid"] = uid
        xml_text = build_chat_cot(msg, now_dt)
        send_udp(xml_text, args.host, args.port)
        sent += 1

        trace.append({
            "seq": idx,
            "uid": uid,
            "from": msg.get("from"),
            "to": msg.get("to"),
            "kind": msg.get("kind"),
            "message": msg.get("message"),
            "meta": msg.get("meta") or {},
            "xml": xml_text,
        })

        time.sleep(0.15)

    overwrite_jsonl(outbox_path, remaining)
    write_json(trace_path, trace)
    print(f"sent={sent}")


if __name__ == "__main__":
    main()
