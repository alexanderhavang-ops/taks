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


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def parse_uid(uid: str) -> Optional[Dict[str, Any]]:
    parts = str(uid or "").split(":")
    if len(parts) < 6:
        return None
    if parts[0] != "replay" or parts[1] != "chat":
        return None

    # replay:chat:<from>:<kind>:<to>:<sim_time_s>:<hash>
    sender = parts[2]
    kind = parts[3]
    recipient = parts[4]

    try:
        sim_time_s = int(parts[5])
    except Exception:
        return None

    return {
        "from": sender,
        "kind": kind,
        "to": recipient,
        "sim_time_s": sim_time_s,
    }


def fetch_recent_chat_rows(callsign: str, lookback_minutes: int) -> List[Dict[str, Any]]:
    sql = f"""
    SELECT
      uid,
      detail::text AS detail_xml
    FROM cot_router
    WHERE uid LIKE 'replay:chat:%'
      AND servertime >= NOW() - INTERVAL '{int(lookback_minutes)} minutes'
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
        rows.append({
            "uid": uid,
            "detail_xml": detail_xml,
        })
    return rows


def extract_taks_chat_json(detail_xml: str) -> Dict[str, Any]:
    start_tag = "<taks_chat"
    end_tag = "</taks_chat>"

    start = detail_xml.find(start_tag)
    if start < 0:
        return {}

    gt = detail_xml.find(">", start)
    if gt < 0:
        return {}

    end = detail_xml.find(end_tag, gt)
    if end < 0:
        return {}

    payload = detail_xml[gt + 1:end].strip()
    if not payload:
        return {}

    try:
        return json.loads(payload)
    except Exception:
        return {}


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

        payload = extract_taks_chat_json(str(row.get("detail_xml") or ""))
        msg = {
            "kind": uid_info["kind"],
            "from": uid_info["from"],
            "to": uid_info["to"],
            "sim_time_s": uid_info["sim_time_s"],
            "message": "",  # NL-text ligger i remarks i CoT, inte i taks_chat-json
            "meta": payload if isinstance(payload, dict) else {},
            "uid": uid,
        }

        append_jsonl(inbox_path, msg)
        seen_set.add(uid)
        imported += 1

    write_json(seen_path, sorted(seen_set))
    print(f"imported={imported}")


if __name__ == "__main__":
    main()
