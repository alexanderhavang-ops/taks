from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from replay_paths import agent_dir, ensure_runtime_dirs

DEFAULT_LOOKBACK_MINUTES = 15


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


def parse_uid(uid: str) -> Optional[Dict[str, Any]]:
    s = str(uid or "")
    if not s.startswith("GeoChat.REPLAY-"):
        return None

    # GeoChat.REPLAY-<from>.<to>.<uuid>
    rest = s[len("GeoChat.REPLAY-"):]
    parts = rest.split(".")
    if len(parts) < 3:
        return None

    sender = parts[0]
    recipient = parts[1]

    return {
        "from": sender,
        "to": recipient,
    }


def fetch_recent_chat_rows(callsign: str, lookback_minutes: int) -> List[Dict[str, Any]]:
    sql = f"""
    SELECT
      uid,
      cot_type,
      sender_callsign,
      dest_callsign,
      dest_uid,
      chat_room,
      chat_content,
      detail::text AS detail_xml
    FROM cot_router_chat
    WHERE servertime >= NOW() - INTERVAL '{int(lookback_minutes)} minutes'
      AND (
        dest_callsign = '{callsign}'
        OR dest_uid = '{callsign}'
        OR chat_room = '{callsign}'
      )
    ORDER BY servertime ASC, id ASC;
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

        parts = line.split("\t", 7)
        if len(parts) != 8:
            continue

        uid, cot_type, sender_callsign, dest_callsign, dest_uid, chat_room, chat_content, detail_xml = parts
        rows.append({
            "uid": uid,
            "cot_type": cot_type,
            "sender_callsign": sender_callsign,
            "dest_callsign": dest_callsign,
            "dest_uid": dest_uid,
            "chat_room": chat_room,
            "chat_content": chat_content,
            "detail_xml": detail_xml,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--callsign", required=True)
    ap.add_argument("--lookback-minutes", type=int, default=DEFAULT_LOOKBACK_MINUTES)
    args = ap.parse_args()

    ensure_runtime_dirs()

    d = agent_dir(args.callsign)
    d.mkdir(parents=True, exist_ok=True)

    inbox_path = d / "inbox.jsonl"
    seen_path = d / "seen_chat_uids.json"

    seen = read_json(seen_path)
    if not isinstance(seen, list):
        seen = []
    seen_set = {str(x) for x in seen}

    rows = fetch_recent_chat_rows(args.callsign, args.lookback_minutes)

    imported = 0
    for row in rows:
        uid = str(row.get("uid") or "")
        if not uid or uid in seen_set:
            continue

        uid_info = parse_uid(uid)
        if not uid_info:
            continue

        sender_callsign = str(row.get("sender_callsign") or uid_info["from"] or "")
        message = str(row.get("chat_content") or "")

        msg = {
            "kind": "order",
            "from": sender_callsign,
            "to": args.callsign,
            "message": message,
            "meta": {},
            "uid": uid,
        }

        append_jsonl(inbox_path, msg)
        seen_set.add(uid)
        imported += 1

    write_json(seen_path, sorted(seen_set))
    print(f"imported={imported}")


if __name__ == "__main__":
    main()
