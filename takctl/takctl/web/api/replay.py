from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/replay", tags=["replay"])

REPO_ROOT = Path("/opt/taks")
REPLAY_SRC = REPO_ROOT / "takctl" / "replay"
RUNTIME_ROOT = Path("/opt/tak/replay")
STATE_ROOT = RUNTIME_ROOT / "state" / "agents"
SEEDS_ROOT = REPLAY_SRC / "seeds"
UI_STATE_PATH = RUNTIME_ROOT / "ui_state.json"

DEFAULT_SCENARIO_ID = "at1_contact_001"
TICK_SEC = 300


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        txt = path.read_text(encoding="utf-8").strip()
        if not txt:
            return default
        return json.loads(txt)
    except Exception:
        return default


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
    except Exception:
        return out
    return out


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _run(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout or "") + "\n" + (proc.stderr or ""))


def _ui_state() -> Dict[str, Any]:
    st = _read_json(UI_STATE_PATH, default={})
    if not isinstance(st, dict):
        st = {}
    st.setdefault("scenario_id", DEFAULT_SCENARIO_ID)
    st.setdefault("current_tick", 0)
    st.setdefault("running", False)
    st.setdefault("order0_override_text_blue", "")
    st.setdefault("order0_override_text_red", "")
    st.setdefault("order0_sent_blue", False)
    st.setdefault("order0_sent_red", False)
    return st


def _save_ui_state(st: Dict[str, Any]) -> None:
    _write_json(UI_STATE_PATH, st)


def _scenario_seed_dir(scenario_id: str) -> Path:
    p = SEEDS_ROOT / scenario_id
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"missing scenario seed dir: {p}")
    return p


def _global_json(scenario_id: str) -> Dict[str, Any]:
    obj = _read_json(_scenario_seed_dir(scenario_id) / "global.json", default={})
    return obj if isinstance(obj, dict) else {}


def _orders_json(scenario_id: str) -> Dict[str, Any]:
    obj = _read_json(_scenario_seed_dir(scenario_id) / "orders.json", default={})
    return obj if isinstance(obj, dict) else {}


def _forces_json(scenario_id: str) -> Dict[str, Any]:
    obj = _read_json(_scenario_seed_dir(scenario_id) / "forces.json", default={})
    return obj if isinstance(obj, dict) else {}


def _initial_orders(scenario_id: str) -> List[Dict[str, Any]]:
    rows = _orders_json(scenario_id).get("initial_orders")
    return list(rows) if isinstance(rows, list) else []


def _default_initial_order(scenario_id: str, side: str) -> Dict[str, Any]:
    orders = _initial_orders(scenario_id)
    side = str(side or "").strip().lower()
    for row in orders:
        if not isinstance(row, dict):
            continue
        row_side = str(row.get("side") or "").strip().lower()
        if row_side == side:
            return dict(row)
    if side == "blue" and orders:
        first = orders[0]
        if isinstance(first, dict):
            return dict(first)
    return {}


def _default_order_text_for_scenario(scenario_id: str, side: str) -> str:
    return str(_default_initial_order(scenario_id, side).get("message") or "")


def _effective_order0_text(scenario_id: str, st: Dict[str, Any], side: str) -> str:
    key = "order0_override_text_blue" if side == "blue" else "order0_override_text_red"
    override = str(st.get(key) or "")
    return override if override.strip() else _default_order_text_for_scenario(scenario_id, side)


def _list_scenarios() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not SEEDS_ROOT.exists():
        return items

    for p in sorted(SEEDS_ROOT.iterdir()):
        if not p.is_dir():
            continue
        scenario_id = p.name
        g = _global_json(scenario_id)
        f = _forces_json(scenario_id)
        title = str(g.get("title") or g.get("name") or scenario_id)
        description = str(g.get("description") or "")
        sides = [k for k in ("blue", "red") if isinstance(f.get(k), dict)]
        items.append({
            "id": scenario_id,
            "title": title,
            "description": description,
            "default_order_text_blue": _default_order_text_for_scenario(scenario_id, "blue"),
            "default_order_text_red": _default_order_text_for_scenario(scenario_id, "red"),
            "sides": sides,
            "has_red_forces": "red" in sides,
        })
    return items


def _load_states() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not STATE_ROOT.exists():
        return out
    for d in sorted(STATE_ROOT.iterdir()):
        if not d.is_dir():
            continue
        st = _read_json(d / "state.json", default={})
        if not isinstance(st, dict):
            continue
        agent = dict(st.get("agent") or {})
        callsign = str(agent.get("callsign") or d.name).strip()
        if callsign:
            out[callsign] = st
    return out


def _tree_from_states(states: Dict[str, Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
    children: Dict[str, List[str]] = {}
    roots: List[str] = []

    for cs, st in states.items():
        agent = dict(st.get("agent") or {})
        if str(agent.get("side") or "") != side:
            continue
        parent = str(agent.get("superior") or "").strip()
        if parent and parent in states and str(dict(states[parent].get("agent") or {}).get("side") or "") == side:
            children.setdefault(parent, []).append(cs)
        else:
            roots.append(cs)

    def build(cs: str) -> Dict[str, Any]:
        st = states.get(cs) or {}
        agent = dict(st.get("agent") or {})
        own = dict(st.get("own_state") or {})
        work = list(st.get("work") or [])
        return {
            "callsign": cs,
            "label": cs,
            "role": str(agent.get("role") or ""),
            "side": str(agent.get("side") or ""),
            "readiness": str(own.get("readiness") or ""),
            "status": "working" if work else "idle",
            "children": [build(k) for k in sorted(children.get(cs, []))],
        }

    return [build(cs) for cs in sorted(roots)]


def _map_markers(states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for cs, st in states.items():
        agent = dict(st.get("agent") or {})
        own = dict(st.get("own_state") or {})
        pos = dict(own.get("position") or {})
        try:
            lat = float(pos.get("lat"))
            lon = float(pos.get("lon"))
        except Exception:
            continue
        items.append({
            "callsign": cs,
            "label": cs,
            "side": str(agent.get("side") or ""),
            "role": str(agent.get("role") or ""),
            "lat": lat,
            "lon": lon,
            "status": "working" if list(st.get("work") or []) else "idle",
        })
    return items


def _unit_detail(st: Dict[str, Any]) -> Dict[str, Any]:
    agent = dict(st.get("agent") or {})
    own = dict(st.get("own_state") or {})
    callsign = str(agent.get("callsign") or "")
    inbox = _read_jsonl(STATE_ROOT / callsign / "inbox.jsonl")
    outbox = _read_jsonl(STATE_ROOT / callsign / "outbox.jsonl")
    return {
        "callsign": callsign,
        "role": str(agent.get("role") or ""),
        "side": str(agent.get("side") or ""),
        "superior": agent.get("superior"),
        "subordinates": [str(x.get("callsign") or "") for x in list(st.get("subordinates") or []) if isinstance(x, dict)],
        "position": dict(own.get("position") or {}),
        "strength": own.get("strength"),
        "ammo": own.get("ammo"),
        "morale": own.get("morale"),
        "posture": own.get("posture"),
        "readiness": own.get("readiness"),
        "combat_value": own.get("combat_value"),
        "status": "working" if list(st.get("work") or []) else "idle",
        "quality": dict(own.get("quality") or {}),
        "work": list(st.get("work") or []),
        "completed_work": list(st.get("completed_work") or []),
        "recent_inbox": inbox[-50:],
        "recent_outbox": outbox[-50:],
        "raw_state": st,
    }


def _global_correspondence(states: Dict[str, Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cs in sorted(states.keys()):
        st = states.get(cs) or {}
        agent = dict(st.get("agent") or {})
        if str(agent.get("side") or "") != side:
            continue

        inbox = _read_jsonl(STATE_ROOT / cs / "inbox.jsonl")
        outbox = _read_jsonl(STATE_ROOT / cs / "outbox.jsonl")

        for i, row in enumerate(inbox):
            rows.append({
                "key": f"in-{cs}-{i}",
                "dir": "in",
                "agent": cs,
                "kind": str(row.get("kind") or ""),
                "from": str(row.get("from") or ""),
                "to": str(row.get("to") or ""),
                "sim_time_s": int(row.get("sim_time_s") or 0),
                "message": str(row.get("message") or ""),
                "uid": str(row.get("uid") or ""),
            })
        for i, row in enumerate(outbox):
            rows.append({
                "key": f"out-{cs}-{i}",
                "dir": "out",
                "agent": cs,
                "kind": str(row.get("kind") or ""),
                "from": str(row.get("from") or ""),
                "to": str(row.get("to") or ""),
                "sim_time_s": int(row.get("sim_time_s") or 0),
                "message": str(row.get("message") or ""),
                "uid": str(row.get("uid") or ""),
            })

    rows.sort(key=lambda r: (int(r.get("sim_time_s") or 0), str(r.get("key") or "")))
    return rows[-400:]


@router.get("/scenarios")
def replay_scenarios() -> Dict[str, Any]:
    return {"items": _list_scenarios()}


@router.get("/state")
def replay_state() -> Dict[str, Any]:
    st = _ui_state()
    scenario_id = str(st.get("scenario_id") or DEFAULT_SCENARIO_ID)
    states = _load_states()
    markers = _map_markers(states)

    center = {"lat": 55.4220, "lon": 13.9180}
    if markers:
        blue_markers = [m for m in markers if m.get("side") == "blue"]
        first = blue_markers[0] if blue_markers else markers[0]
        center = {"lat": first["lat"], "lon": first["lon"]}

    units = {cs: _unit_detail(v) for cs, v in states.items()}

    return {
        "scenario": {
            "id": scenario_id,
            "title": str(_global_json(scenario_id).get("title") or scenario_id),
        },
        "runtime": {
            "exists": STATE_ROOT.exists(),
            "running": False,
            "tick_mode": "manual",
            "current_tick": int(st.get("current_tick") or 0),
            "tick_interval_sec": TICK_SEC,
            "last_updated": None,
        },
        "controls": {
            "can_reset": True,
            "can_tick": True,
            "can_send_order0": True,
        },
        "initial_orders": {
            "blue": {
                "editable": True,
                "sent": bool(st.get("order0_sent_blue")),
                "text": _effective_order0_text(scenario_id, st, "blue"),
            },
            "red": {
                "editable": True,
                "sent": bool(st.get("order0_sent_red")),
                "text": _effective_order0_text(scenario_id, st, "red"),
            },
        },
        "map": {
            "center": center,
            "zoom": 14 if scenario_id == "at1_contact_001" else 10,
            "markers": markers,
        },
        "trees": {
            "blue": _tree_from_states(states, "blue"),
            "red": _tree_from_states(states, "red"),
        },
        "units": units,
        "chat_by_side": {
            "blue": _global_correspondence(states, "blue"),
            "red": _global_correspondence(states, "red"),
        },
    }


@router.post("/order0")
async def replay_update_order0(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}

    side = str((body or {}).get("side") or "blue").strip().lower()
    if side not in {"blue", "red"}:
        raise HTTPException(status_code=400, detail="side must be blue or red")

    st = _ui_state()
    text = str((body or {}).get("text") or "")
    key = "order0_override_text_blue" if side == "blue" else "order0_override_text_red"
    st[key] = text
    _save_ui_state(st)
    return {"ok": True, "side": side, "text": text}


@router.post("/reset")
async def replay_reset(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}

    scenario_id = str((body or {}).get("scenario_id") or DEFAULT_SCENARIO_ID).strip()
    if not scenario_id:
        scenario_id = DEFAULT_SCENARIO_ID

    try:
        _scenario_seed_dir(scenario_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        _run([
            "env", "PYTHONPATH=/opt/taks/takctl",
            "python3", "takctl/replay/launch_seed.py",
            "--seed-dir", scenario_id,
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"reset failed: {e}")

    st = {
        "scenario_id": scenario_id,
        "current_tick": 0,
        "running": False,
        "order0_override_text_blue": "",
        "order0_override_text_red": "",
        "order0_sent_blue": False,
        "order0_sent_red": False,
    }
    _save_ui_state(st)

    return {"ok": True, "scenario_id": scenario_id, "current_tick": 0}


@router.post("/send_order0")
async def replay_send_order0(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}

    side = str((body or {}).get("side") or "blue").strip().lower()
    if side not in {"blue", "red"}:
        raise HTTPException(status_code=400, detail="side must be blue or red")

    st = _ui_state()
    scenario_id = str(st.get("scenario_id") or DEFAULT_SCENARIO_ID)
    initial = _default_initial_order(scenario_id, side)
    recipient = str((body or {}).get("to") or initial.get("to") or "").strip()
    sender = str(initial.get("from") or "")
    intent = initial.get("intent")
    issued_tnr = initial.get("issued_tnr")
    language = initial.get("language")
    message = str((body or {}).get("text") or _effective_order0_text(scenario_id, st, side) or "").strip()

    if not recipient:
        raise HTTPException(status_code=400, detail=f"missing initial order recipient for side={side}")
    if not message:
        raise HTTPException(status_code=400, detail="missing order text")

    inbox_path = STATE_ROOT / recipient / "inbox.jsonl"
    if not inbox_path.parent.exists():
        raise HTTPException(status_code=404, detail=f"recipient not seeded: {recipient}")

    _append_jsonl(inbox_path, {
        "kind": "order",
        "from": sender,
        "to": recipient,
        "sim_time_s": int(st.get("current_tick") or 0) * TICK_SEC,
        "message": message,
        "meta": {
            "intent": intent,
            "issued_tnr": issued_tnr,
            "language": language,
            "manual_send": True,
            "side": side,
        },
    })

    st["order0_sent_blue" if side == "blue" else "order0_sent_red"] = True
    _save_ui_state(st)

    return {"ok": True, "side": side, "sent_to": recipient}


@router.post("/tick")
async def replay_tick(req: Request) -> Dict[str, Any]:
    try:
        await req.json()
    except Exception:
        pass

    st = _ui_state()
    current_tick = int(st.get("current_tick") or 0)
    sim_time = current_tick * TICK_SEC

    try:
        _run([
            "env", "PYTHONPATH=/opt/taks/takctl",
            "python3", "takctl/replay/run_sim_tick.py",
            "--sim-time", str(sim_time),
            "--temperature", "0.2",
            "--max-tokens", "2000",
            "--seed", "7",
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tick failed: {e}")

    st["current_tick"] = current_tick + 1
    _save_ui_state(st)

    return {"ok": True, "current_tick": st["current_tick"], "running": False}
