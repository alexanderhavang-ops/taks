from __future__ import annotations

import argparse
import json
import random
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from replay_paths import SEED_ROOT, agent_dir, ensure_runtime_dirs


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clear_agent_dir(callsign: str) -> None:
    d = agent_dir(callsign)
    d.mkdir(parents=True, exist_ok=True)
    for name in [
        "state.json",
        "inbox.jsonl",
        "outbox.jsonl",
        "decisions.jsonl",
        "tasks.jsonl",
        "last_packet.json",
        "last_system_prompt.txt",
        "last_user_prompt.txt",
        "last_full_prompt.txt",
        "last_llm_response.txt",
        "llm_trace.log",
        "seen_chat_uids.json",
        "emit_trace.json",
    ]:
        p = d / name
        if p.exists():
            p.unlink()



def clear_all_agent_dirs() -> None:
    root = agent_dir("__dummy__").parent
    if not root.exists():
        return
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
def build_children(units: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for u in units:
        parent = u.get("parent")
        cs = str(u["callsign"])
        if parent is None:
            continue
        out.setdefault(str(parent), []).append(cs)
    return out


def find_order_for(callsign: str, orders: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for o in orders:
        if str(o.get("to") or "") == callsign:
            return o
    return None


def select_forces_path(seed_dir: Path) -> Path:
    generated = seed_dir / "forces.generated.json"
    plain = seed_dir / "forces.json"
    if generated.exists():
        return generated
    return plain


def control_mode_for_role(role: str) -> str:
    role = str(role or "")
    if role in {"platoon", "group"}:
        return "llm"
    return "simulated"


def decision_profile_for_role(role: str) -> Dict[str, Any]:
    role = str(role or "")
    if role in {"battalion", "company", "platoon", "group", "staff_tross_platoon"}:
        return {
            "decision_policy": "on_change",
            "decision_horizon_source": "global",
            "status_interval_sec": 1800,
            "run_if_idle": False,
            "next_decision_due_sim_time_s": 0,
        }
    return {
        "decision_policy": "simulated",
        "decision_horizon_source": "none",
        "status_interval_sec": 0,
        "run_if_idle": False,
        "next_decision_due_sim_time_s": None,
    }


def build_mission(role: str, parent: Optional[str]) -> str:
    if str(role) == "battalion":
        return "Lös tilldelad uppgift enligt högre chefs order."
    if parent:
        return f"Lös uppgift inom ramen för {parent}:s order."
    return "Lös tilldelad uppgift."


def doctrinal_function_for_unit(callsign: str, role: str) -> str:
    cs = str(callsign or "").upper()
    r = str(role or "")

    if r == "battalion":
        return "hq"
    if r == "company" and cs == "PQ":
        return "hq"
    if r == "staff_tross_platoon":
        return "logistics"
    if r in {"company", "platoon", "group"}:
        return "battle_unit"
    return "support"


def capabilities_for_function(function_name: str) -> Dict[str, Any]:
    fn = str(function_name or "")
    if fn == "hq":
        return {
            "command_and_control": True,
            "direct_combat": False,
            "sustainment": False,
            "repair": False,
            "medical": False,
        }
    if fn == "battle_unit":
        return {
            "command_and_control": False,
            "direct_combat": True,
            "sustainment": False,
            "repair": False,
            "medical": False,
        }
    if fn == "logistics":
        return {
            "command_and_control": False,
            "direct_combat": False,
            "sustainment": True,
            "repair": False,
            "medical": False,
        }
    return {
        "command_and_control": False,
        "direct_combat": False,
        "sustainment": False,
        "repair": False,
        "medical": False,
    }


def command_profile_for_unit(callsign: str, role: str, function_name: str) -> Dict[str, Any]:
    cs = str(callsign or "").upper()
    if role == "battalion":
        return {"max_control_distance_km": 80}
    if cs == "PQ":
        return {"max_control_distance_km": 100}
    if function_name == "battle_unit":
        return {"max_control_distance_km": 25}
    return {"max_control_distance_km": 30}


def mobility_profile_for_unit(callsign: str, role: str, function_name: str, base: Dict[str, Any]) -> Dict[str, Any]:
    cs = str(callsign or "").upper()
    m = dict(base or {})

    if role == "battalion":
        m.setdefault("type", "mixed")
        m.setdefault("speed_kph_max", 80)
        m["mobility_policy"] = "mobile_hq"
        m["setup_time_s"] = 3600
        m["teardown_time_s"] = 3600
        return m

    if cs == "PQ":
        m["type"] = "staff_command"
        m.setdefault("speed_kph_max", 80)
        m["mobility_policy"] = "static_unless_required"
        m["setup_time_s"] = 10800
        m["teardown_time_s"] = 10800
        return m

    if function_name == "logistics":
        m.setdefault("type", "truck")
        m.setdefault("speed_kph_max", 70)
        m["mobility_policy"] = "support_move"
        m["setup_time_s"] = 900
        m["teardown_time_s"] = 900
        return m

    if role == "platoon":
        m.setdefault("type", "bandvagn")
        m.setdefault("speed_kph_max", 50)
        m["terrain_mobility"] = "good"
        m["mobility_policy"] = "maneuver"
        m["setup_time_s"] = 300
        m["teardown_time_s"] = 300
        return m

    if role == "group":
        m.setdefault("type", "foot_mobile")
        m.setdefault("speed_kph_max", 5)
        m["mobility_policy"] = "dismounted"
        m["setup_time_s"] = 120
        m["teardown_time_s"] = 120
        return m

    m.setdefault("mobility_policy", "maneuver")
    m.setdefault("setup_time_s", 300)
    m.setdefault("teardown_time_s", 300)
    return m


def seeded_quality(callsign: str) -> Dict[str, int]:
    rng = random.Random(f"ystad-001:{callsign}")
    leader = rng.randint(40, 90)
    unit = max(25, min(95, leader + rng.randint(-12, 8)))
    cohesion = max(20, min(99, unit + rng.randint(-8, 12)))
    discipline = max(20, min(99, leader + rng.randint(-10, 15)))
    initiative = max(20, min(99, unit + rng.randint(-12, 10)))
    return {
        "leader_experience": leader,
        "unit_experience": unit,
        "cohesion": cohesion,
        "discipline": discipline,
        "initiative": initiative,
    }


def seconds_to_tnr(sim_time_s: int) -> str:
    total_minutes = int(sim_time_s // 60)
    day = 17 + (total_minutes // (24 * 60))
    hh = (total_minutes % (24 * 60)) // 60
    mm = total_minutes % 60
    return f"{day:02d}{hh:02d}{mm:02d}"


_TNR_TOKEN_RE = re.compile(r"T0\+(\d+)")


def render_tnr_tokens(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            return seconds_to_tnr(int(m.group(1)))
        return _TNR_TOKEN_RE.sub(repl, value)
    if isinstance(value, list):
        return [render_tnr_tokens(x) for x in value]
    if isinstance(value, dict):
        return {k: render_tnr_tokens(v) for k, v in value.items()}
    return value



def seed_agent_states(seed_dir: Path) -> None:
    ensure_runtime_dirs()
    clear_all_agent_dirs()

    global_cfg = read_json(seed_dir / "global.json")
    forces_path = select_forces_path(seed_dir)
    forces = read_json(forces_path)
    orders_cfg = read_json(seed_dir / "orders.json")

    initial_orders = list(orders_cfg.get("initial_orders") or [])
    decision_horizon_sec = int(global_cfg.get("decision_horizon_sec") or 300)
    weather = dict(global_cfg.get("weather") or {})

    total_units = 0
    total_strength = 0
    total_llm = 0

    for side_name in ("blue", "red"):
        side = dict(forces.get(side_name) or {})
        side_units = list(side.get("units") or [])
        children = build_children(side_units)

        if side_name == "blue":
            default_lang = "sv-se-military"
            default_doctrine = "swedish-home-guard"
            roe_value = str((global_cfg.get("roe") or {}).get("blue") or "defensiv")
        else:
            default_lang = "ru-military"
            default_doctrine = "russian-amphibious"
            roe_value = str((global_cfg.get("roe") or {}).get("red") or "offensiv")

        language_profile_default = str(side.get("language_profile") or default_lang)
        doctrine_profile_default = str(side.get("doctrine_profile") or default_doctrine)

        side_count = 0
        side_strength = 0
        side_llm = 0

        for u in side_units:
            callsign = str(u["callsign"])
            clear_agent_dir(callsign)

            pos = dict(u.get("position") or {})
            parent = u.get("parent")
            role = str(u.get("role") or "unit")
            strength = int(u.get("strength") or 0)
            readiness = str(u.get("readiness") or "okänd")
            combat_value = str(u.get("combat_value") or "okänt")
            mobility = dict(u.get("mobility") or {})
            language_profile = str(u.get("language_profile") or language_profile_default)
            doctrine_profile = str(u.get("doctrine_profile") or doctrine_profile_default)
            control_mode = control_mode_for_role(role)

            function_name = doctrinal_function_for_unit(callsign, role)
            capabilities = capabilities_for_function(function_name)
            command_profile = command_profile_for_unit(callsign, role, function_name)
            mobility_profile = mobility_profile_for_unit(callsign, role, function_name, mobility)
            quality = seeded_quality(callsign)

            subs = []
            for child_cs in children.get(callsign, []):
                subs.append({
                    "callsign": child_cs,
                    "status": "ok",
                })

            state = {
                "agent": {
                    "callsign": callsign,
                    "role": role,
                    "function": function_name,
                    "side": side_name,
                    "superior": parent,
                    "mission": build_mission(role, parent),
                    "language_profile": language_profile,
                    "doctrine_profile": doctrine_profile,
                    "control_mode": control_mode,
                    "capabilities": capabilities,
                    "command_profile": command_profile,
                },
                "own_state": {
                    "position": {
                        "lat": pos.get("lat"),
                        "lon": pos.get("lon"),
                    },
                    "strength": strength,
                    "ammo": "tillräcklig",
                    "morale": "stabil",
                    "posture": "utgångsgrupperad",
                    "readiness": readiness,
                    "combat_value": combat_value,
                    "mobility": mobility_profile,
                    "quality": quality,
                    "weather": weather,
                },
                "subordinates": subs,
                "observations": [],
                "constraints": {
                    "roe": roe_value,
                    "decision_horizon_sec": decision_horizon_sec,
                },
                "work": [],
                "completed_work": [],
            }

            d = agent_dir(callsign)
            write_json(d / "state.json", state)
            write_jsonl(d / "inbox.jsonl", [])
            write_jsonl(d / "outbox.jsonl", [])
            write_jsonl(d / "decisions.jsonl", [])
            write_jsonl(d / "tasks.jsonl", [])
            write_json(d / "seen_chat_uids.json", [])

            top_order = find_order_for(callsign, initial_orders)
            if top_order is not None:
                rendered_order = render_tnr_tokens(top_order)
                inbox_msg = {
                    "kind": "order",
                    "from": str(rendered_order.get("from") or ""),
                    "to": callsign,
                    "sim_time_s": int(rendered_order.get("sim_time_s") or 0),
                    "message": str(rendered_order.get("message") or ""),
                    "meta": {
                        "intent": rendered_order.get("intent"),
                        "issued_tnr": rendered_order.get("issued_tnr"),
                        "language": rendered_order.get("language"),
                        "seed_order": True,
                    },
                }
                write_jsonl(d / "inbox.jsonl", [inbox_msg])

            side_count += 1
            side_strength += strength
            if control_mode == "llm":
                side_llm += 1

        total_units += side_count
        total_strength += side_strength
        total_llm += side_llm

        print(
            "SEEDED_SIDE "
            f"side={side_name} "
            f"units={side_count} "
            f"llm={side_llm} "
            f"total_strength={side_strength}"
        )

    print(
        "SEEDED_TOTAL "
        f"units={total_units} "
        f"llm={total_llm} "
        f"total_strength={total_strength}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-dir", required=True, help="Path to seed directory")
    args = ap.parse_args()

    seed_dir = Path(args.seed_dir)
    if not seed_dir.is_absolute():
        seed_dir = SEED_ROOT / seed_dir

    seed_agent_states(seed_dir)


if __name__ == "__main__":
    main()
