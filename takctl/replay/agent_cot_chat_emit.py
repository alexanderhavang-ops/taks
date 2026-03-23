from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def make_uid(msg: Dict[str, Any]) -> str:
    return (
        f"replay:chat:"
        f"{msg.get('from','unknown')}:"
        f"{msg.get('kind','message')}:"
        f"{msg.get('to','unknown')}:"
        f"{int(msg.get('sim_time_s') or 0)}:"
        f"{abs(hash(json.dumps(msg, ensure_ascii=False, sort_keys=True))) % 10_000_000}"
    )


def build_chat_cot(msg: Dict[str, Any], now_dt: datetime) -> str:
    uid = str(msg.get("uid") or make_uid(msg))
    frm = str(msg.get("from") or "")
    message = str(msg.get("message") or "")

    remarks = escape(message)

    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-m-p-s-p-op" how="m-g" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.422000" lon="13.918000" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<contact callsign="{escape(frm)}-CHAT" endpoint="*:-1:stcp"/>'
        f'<__group name="Cyan" role="Team Member"/>'
        f'<remarks>{remarks}</remarks>'
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
            "sim_time_s": msg.get("sim_time_s"),
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
