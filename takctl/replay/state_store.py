from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from replay_paths import STATE_ROOT, agent_dir, ensure_runtime_dirs


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    txt = path.read_text(encoding='utf-8').strip()
    if not txt:
        return default
    try:
        return json.loads(txt)
    except Exception:
        return default


def write_json(path: Path, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def overwrite_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    text = ''.join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows if isinstance(row, dict))
    _atomic_write_text(path, text)


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def ensure_state_schema(st: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(st, dict):
        st = {}
    st.pop('current_activity', None)
    st.setdefault('agent', {})
    st.setdefault('own_state', {})
    st.setdefault('subordinates', [])
    st.setdefault('constraints', {})
    st.setdefault('work', [])
    st.setdefault('completed_work', [])
    st.setdefault('new_messages', [])
    st.setdefault('read_messages', [])
    st.setdefault('inbox', [])
    st.setdefault('seen_chat_uids', [])
    st.setdefault('private_referee', [])
    st.setdefault('pending_report_items', [])
    st.setdefault('world_changed_this_tick', False)
    st.setdefault('last_referee_outcome', {})
    return _strip_legacy_forbidden_fields(st)


def message_token(row: Dict[str, Any]) -> str:
    row = dict(row or {})
    uid = str(row.get('uid') or '').strip()
    if uid:
        return uid
    meta = dict(row.get('meta') or {})
    return '|'.join([
        str(row.get('kind') or ''),
        str(row.get('from') or ''),
        str(row.get('to') or ''),
        str(row.get('sim_time_s') or ''),
        str(meta.get('issued_tnr') or ''),
        str(row.get('message') or ''),
    ])


def ensure_agent_layout(callsign: str) -> Path:
    ensure_runtime_dirs()
    d = agent_dir(callsign)
    d.mkdir(parents=True, exist_ok=True)
    for name, default in [
        ('state.json', {}),
        ('inbox.jsonl', None),
        ('outbox.jsonl', None),
        ('decisions.jsonl', None),
        ('tasks.jsonl', None),
    ]:
        p = d / name
        if p.exists():
            continue
        if name.endswith('.json'):
            write_json(p, default)
        else:
            _atomic_write_text(p, '')
    return d



def _strip_legacy_forbidden_fields(st):
    if not isinstance(st, dict):
        return st
    st.pop("current_activity", None)

    work = []
    for chain in list(st.get("work") or []):
        if not isinstance(chain, list):
            continue
        out_chain = []
        for item in chain:
            if not isinstance(item, dict):
                continue
            x = dict(item)
            out_chain.append(x)
        if out_chain:
            work.append(out_chain)
    st["work"] = work

    completed = []
    for item in list(st.get("completed_work") or []):
        if not isinstance(item, dict):
            continue
        x = dict(item)
        completed.append(x)
    st["completed_work"] = completed
    return st

def load_state(callsign: str) -> Dict[str, Any]:
    d = ensure_agent_layout(callsign)
    st = read_json(d / 'state.json', {})
    st = st if isinstance(st, dict) else {}
    st = _strip_legacy_forbidden_fields(st)
    return ensure_state_schema(st)


def save_state(callsign: str, st: Dict[str, Any]) -> None:
    d = ensure_agent_layout(callsign)
    st = _strip_legacy_forbidden_fields(st if isinstance(st, dict) else {})
    write_json(d / 'state.json', ensure_state_schema(st))


def move_new_messages_to_read(st: Dict[str, Any]) -> Dict[str, Any]:
    st = ensure_state_schema(st)
    pending = list(st.get('new_messages') or [])
    if pending:
        read_hist = list(st.get('read_messages') or [])
        read_hist.extend(pending)
        st['read_messages'] = read_hist[-500:]
    st['new_messages'] = []
    st['inbox'] = []
    return st


def consume_transport_inbox(callsign: str) -> Dict[str, Any]:
    st = load_state(callsign)
    d = ensure_agent_layout(callsign)
    inbox_path = d / 'inbox.jsonl'
    rows = read_jsonl(inbox_path)
    overwrite_jsonl(inbox_path, [])

    existing_new = list(st.get('new_messages') or [])
    existing_read = list(st.get('read_messages') or [])
    existing_seen = [str(x) for x in list(st.get('seen_chat_uids') or [])]
    seen = set(existing_seen)
    existing_new_tokens = {message_token(x) for x in existing_new if isinstance(x, dict)}
    existing_read_tokens = {message_token(x) for x in existing_read if isinstance(x, dict)}

    appended: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tok = message_token(row)
        if tok in existing_new_tokens or tok in existing_read_tokens:
            continue
        msg = dict(row)
        msg['_message_token'] = tok
        appended.append(msg)
        if tok not in seen:
            existing_seen.append(tok)
            seen.add(tok)

    st['new_messages'] = (existing_new + appended)[-500:]
    st['inbox'] = list(st.get('new_messages') or [])
    st['seen_chat_uids'] = existing_seen[-2000:]
    save_state(callsign, st)
    return st


def queue_message_to_unit(recipient: str, msg: Dict[str, Any]) -> None:
    d = ensure_agent_layout(recipient)
    append_jsonl(d / 'inbox.jsonl', msg)


def append_outbox_message(callsign: str, msg: Dict[str, Any]) -> None:
    d = ensure_agent_layout(callsign)
    append_jsonl(d / 'outbox.jsonl', msg)


def load_all_states() -> Dict[str, Dict[str, Any]]:
    ensure_runtime_dirs()
    out: Dict[str, Dict[str, Any]] = {}
    if not STATE_ROOT.exists():
        return out
    for d in sorted(STATE_ROOT.iterdir()):
        if not d.is_dir():
            continue
        p = d / 'state.json'
        if not p.exists():
            continue
        st = read_json(p, {})
        if not isinstance(st, dict):
            continue
        st = _strip_legacy_forbidden_fields(st)
        st = _strip_legacy_forbidden_fields(ensure_state_schema(st))
        cs = str((st.get('agent') or {}).get('callsign') or d.name).upper()
        out[cs] = st
    return out
