from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from martine.agent.simple_agent import run_once
from martine.state.paths import ensure_state_dirs, martine_state_dir


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6969
DEFAULT_LOOKBACK_MINUTES = 15


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return None
    return json.loads(txt)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def cot_runtime_dir() -> Path:
    root = martine_state_dir()
    d = root / "cot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_uid(uid: str) -> Optional[Dict[str, Any]]:
    parts = str(uid or "").split(":")
    if len(parts) < 6:
        return None
    if parts[0] != "replay" or parts[1] != "chat":
        return None
    try:
        sim_time_s = int(parts[5])
    except Exception:
        return None
    return {
        "from": parts[2],
        "kind": parts[3],
        "to": parts[4],
        "sim_time_s": sim_time_s,
    }


def fetch_recent_chat_rows(callsign: str, lookback_minutes: int) -> List[Dict[str, Any]]:
    sql = f"""
    SELECT
      uid,
      detail::text AS detail_xml
    FROM cot_router
    WHERE servertime >= NOW() - INTERVAL '{int(lookback_minutes)} minutes'
      AND detail::text LIKE '%<taks_chat %'
      AND detail::text LIKE '%to="{callsign}"%'
    ORDER BY servertime ASC, uid ASC;
    """
    cmd = [
        "sudo", "-u", "postgres",
        "psql", "-d", "cot",
        "-P", "pager=off",
        "-A", "-F", "\t",
        "-t",
        "-c", sql,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    rows: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        uid, detail_xml = parts
        rows.append({"uid": uid, "detail_xml": detail_xml})
    return rows


def parse_detail(detail_xml: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"message": "", "meta": {}, "chat": {}}
    if not detail_xml.strip():
        return out
    try:
        root = ET.fromstring(f"<root>{detail_xml}</root>")
    except Exception:
        return out

    remarks = root.find(".//remarks")
    if remarks is not None and remarks.text:
        out["message"] = str(remarks.text)

    taks_chat = root.find(".//taks_chat")
    if taks_chat is not None:
        out["chat"] = dict(taks_chat.attrib)
        payload = (taks_chat.text or "").strip()
        if payload:
            try:
                out["meta"] = json.loads(payload)
            except Exception:
                out["meta"] = {"raw": payload}

    return out


def make_reply_uid(frm: str, to: str, question_uid: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tail = abs(hash(question_uid)) % 10_000_000
    return f"martine:chat:{frm}:reply:{to}:{stamp}:{tail}"


def build_chat_cot(frm: str, to: str, message: str, meta: Dict[str, Any], uid: str, now_dt: datetime) -> str:
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    meta_json = escape(json.dumps(meta, ensure_ascii=False))
    remarks = escape(message)

    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-m-p-s-p-op" how="m-g" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.422000" lon="13.918000" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<contact callsign="{escape(frm)}-CHAT" endpoint="*:-1:stcp"/>'
        f'<__group name="Cyan" role="Team Member"/>'
        f'<remarks>{remarks}</remarks>'
        f'<taks_chat from="{escape(frm)}" to="{escape(to)}" kind="reply">{meta_json}</taks_chat>'
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


def run_once_cot(callsign: str, host: str, port: int, lookback_minutes: int) -> Dict[str, Any]:
    ensure_state_dirs()
    d = cot_runtime_dir()
    seen_path = d / "seen_chat_uids.json"
    inbox_path = d / "inbox.jsonl"
    outbox_trace_path = d / "emit_trace.json"

    seen = read_json(seen_path)
    if not isinstance(seen, list):
        seen = []
    seen_set = {str(x) for x in seen}

    rows = fetch_recent_chat_rows(callsign, lookback_minutes)
    imported = 0
    replied = 0
    trace: List[Dict[str, Any]] = []

    for row in rows:
        uid = str(row.get("uid") or "")
        if not uid or uid in seen_set:
            continue

        uid_info = parse_uid(uid) or {}
        detail = parse_detail(str(row.get("detail_xml") or ""))
        question = str(detail.get("message") or "").strip()
        sender = str(uid_info.get("from") or detail.get("chat", {}).get("from") or "")
        recipient = str(uid_info.get("to") or detail.get("chat", {}).get("to") or "")

        imported_msg = {
            "uid": uid,
            "from": sender,
            "to": recipient,
            "kind": str(uid_info.get("kind") or detail.get("chat", {}).get("kind") or "message"),
            "sim_time_s": uid_info.get("sim_time_s"),
            "message": question,
            "meta": detail.get("meta") or {},
        }
        append_jsonl(inbox_path, imported_msg)
        imported += 1
        seen_set.add(uid)

        if not question:
            trace.append({
                "uid": uid,
                "status": "ignored_empty_question",
                "from": sender,
                "to": recipient,
            })
            continue

        result = run_once(question)
        answer = str(result.get("answer") or "").strip()
        if not answer:
            answer = f"Jag kunde inte svara just nu. Fel: {result.get('error') or 'okänt fel'}"

        reply_uid = make_reply_uid(callsign, sender or "unknown", uid)
        meta = {
            "question_uid": uid,
            "run_id": result.get("run_id"),
            "selection": result.get("selection") or {},
        }
        now_dt = datetime.now(timezone.utc)
        xml_text = build_chat_cot(
            frm=callsign,
            to=sender or "unknown",
            message=answer,
            meta=meta,
            uid=reply_uid,
            now_dt=now_dt,
        )
        send_udp(xml_text, host, port)
        replied += 1

        trace.append({
            "question_uid": uid,
            "reply_uid": reply_uid,
            "from": callsign,
            "to": sender,
            "question": question,
            "answer": answer,
            "run_id": result.get("run_id"),
            "xml": xml_text,
        })

        time.sleep(0.15)

    write_json(seen_path, sorted(seen_set))
    write_json(outbox_trace_path, trace)

    return {
        "ok": True,
        "callsign": callsign,
        "imported": imported,
        "replied": replied,
        "seen_path": str(seen_path),
        "inbox_path": str(inbox_path),
        "emit_trace_path": str(outbox_trace_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--callsign", default="Martine")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--lookback-minutes", type=int, default=DEFAULT_LOOKBACK_MINUTES)
    args = ap.parse_args()

    result = run_once_cot(
        callsign=str(args.callsign),
        host=str(args.host),
        port=int(args.port),
        lookback_minutes=int(args.lookback_minutes),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
