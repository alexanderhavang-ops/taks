from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
if str(SCRIPT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT.parent))
from typing import Any, Dict, List, Tuple

from referee_guardrails import haversine_km
from replay_paths import SEED_ROOT, STATE_ROOT
from state_store import load_state, save_state

UI_STATE_PATH = Path("/opt/tak/replay/ui_state.json")
DEFAULT_OBSERVE_DISTANCE_KM = 0.75
DEFAULT_CONTACT_DISTANCE_KM = 0.25


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return {}
    obj = json.loads(txt)
    return obj if isinstance(obj, dict) else {}


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scenario_id() -> str:
    ui = read_json(UI_STATE_PATH)
    return str(ui.get("scenario_id") or "at1_contact_001")


def referee_cfg() -> Dict[str, Any]:
    sid = scenario_id()
    return dict((read_json(SEED_ROOT / sid / "global.json").get("referee") or {}))


def iter_states() -> List[Tuple[str, Dict[str, Any], Path]]:
    out = []
    if not STATE_ROOT.exists():
        return out
    for d in sorted(STATE_ROOT.iterdir()):
        if not d.is_dir():
            continue
        p = d / "state.json"
        if not p.exists():
            continue
        st = load_state(d.name)
        agent = dict(st.get("agent") or {})
        callsign = str(agent.get("callsign") or d.name).upper()
        out.append((callsign, st, p))
    return out


def unit_pos(st: Dict[str, Any]) -> Dict[str, float] | None:
    pos = dict((st.get("own_state") or {}).get("position") or {})
    try:
        return {"lat": float(pos.get("lat")), "lon": float(pos.get("lon"))}
    except Exception:
        return None


def append_unique_observation(st: Dict[str, Any], obs: Dict[str, Any]) -> bool:
    rows = list(st.get("observations") or [])
    token = json.dumps(obs, ensure_ascii=False, sort_keys=True)
    existing = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in rows if isinstance(x, dict)}
    if token in existing:
        return False
    rows.append(obs)
    st["observations"] = rows[-200:]
    return True


def mark_world_changed(st: Dict[str, Any], summary: str, sim_time_s: int) -> None:
    st["world_changed_this_tick"] = True
    priv = list(st.get("private_referee") or [])
    priv.append({"sim_time_s": int(sim_time_s), "summary": summary})
    st["private_referee"] = priv[-100:]
    st["last_referee_outcome"] = {
        "sim_time_s": int(sim_time_s),
        "summary": summary,
        "activity_result": "world_change",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-time", type=int, required=True)
    ap.add_argument("--blue-callsigns", default="")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    del args.temperature, args.max_tokens, args.seed

    cfg = referee_cfg()
    observe_distance_km = float(cfg.get("observation_distance_km") or DEFAULT_OBSERVE_DISTANCE_KM)
    contact_distance_km = float(cfg.get("contact_distance_km") or DEFAULT_CONTACT_DISTANCE_KM)

    selected_blue = {x.strip().upper() for x in args.blue_callsigns.split(",") if x.strip()}

    states = iter_states()
    blue: List[Tuple[str, Dict[str, Any], Path]] = []
    red: List[Tuple[str, Dict[str, Any], Path]] = []
    for cs, st, p in states:
        side = str((st.get("agent") or {}).get("side") or "").lower()
        if side == "blue":
            if selected_blue and cs not in selected_blue:
                continue
            blue.append((cs, st, p))
        elif side == "red":
            red.append((cs, st, p))

    changed = 0
    considered = 0

    for _, st, p in states:
        st["world_changed_this_tick"] = False
        save_state(str((st.get("agent") or {}).get("callsign") or p.parent.name), st)

    for bcs, bst, bp in blue:
        bpos = unit_pos(bst)
        if not bpos:
            continue
        for rcs, rst, rp in red:
            rpos = unit_pos(rst)
            if not rpos:
                continue
            dist_km = haversine_km(bpos, rpos)
            if dist_km > observe_distance_km:
                continue
            considered += 1
            relation = "contact" if dist_km <= contact_distance_km else "observation"
            bobs = {
                "kind": "referee_enemy_presence",
                "sim_time_s": int(args.sim_time),
                "subject": rcs,
                "distance_km": round(dist_km, 3),
                "relation": relation,
                "position": dict(rpos),
                "summary": f"{rcs} within {round(dist_km, 3)} km of {bcs}",
            }
            robs = {
                "kind": "referee_enemy_presence",
                "sim_time_s": int(args.sim_time),
                "subject": bcs,
                "distance_km": round(dist_km, 3),
                "relation": relation,
                "position": dict(bpos),
                "summary": f"{bcs} within {round(dist_km, 3)} km of {rcs}",
            }
            b_changed = append_unique_observation(bst, bobs)
            r_changed = append_unique_observation(rst, robs)
            if b_changed:
                mark_world_changed(bst, bobs["summary"], args.sim_time)
                save_state(bcs, bst)
                changed += 1
            if r_changed:
                mark_world_changed(rst, robs["summary"], args.sim_time)
                save_state(rcs, rst)
                changed += 1

    print(f"pairs_considered={considered}")
    print(f"states_changed={changed}")


if __name__ == "__main__":
    main()
