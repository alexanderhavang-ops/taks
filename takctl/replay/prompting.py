from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

PROMPT_ROOT = Path("/opt/tak/tools/takctl/replay/prompts")

LEGACY_SYSTEM_PROMPT_PATH = PROMPT_ROOT / "system" / "base_system.txt"
LEGACY_USER_PROMPT_PATH = PROMPT_ROOT / "user" / "agent_user.txt"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _subordinate_names(packet: Dict[str, object]) -> str:
    subs = list(packet.get("subordinates") or [])
    names = [str(x.get("callsign") or "").strip() for x in subs if isinstance(x, dict)]
    names = [x for x in names if x]
    return ", ".join(names) if names else "(inga)"


def _safe_name(v: object, default: str) -> str:
    s = str(v or "").strip()
    if not s:
        return default
    return s


def _profile_root(packet: Dict[str, object]) -> Path:
    agent = dict(packet.get("agent") or {})
    doctrine_profile = _safe_name(agent.get("doctrine_profile"), "swedish_home_guard")
    doctrine_profile = doctrine_profile.replace("-", "_")
    return PROMPT_ROOT / doctrine_profile


def _existing_paths(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.exists()]


def _render_template(text: str, mapping: Dict[str, str]) -> str:
    out = text
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out


def _system_prompt_paths(packet: Dict[str, object]) -> List[Path]:
    agent = dict(packet.get("agent") or {})
    profile_root = _profile_root(packet)

    role = _safe_name(agent.get("role"), "unit")
    function_name = _safe_name(agent.get("function"), "generic")

    preferred = [
        profile_root / "system" / "base_system.txt",
        profile_root / "system" / "functions" / f"{function_name}.txt",
        profile_root / "system" / "roles" / f"{role}.txt",
    ]
    preferred_existing = _existing_paths(preferred)
    if preferred_existing:
        return preferred_existing

    return [LEGACY_SYSTEM_PROMPT_PATH]


def _user_prompt_path(packet: Dict[str, object]) -> Path:
    profile_root = _profile_root(packet)
    preferred = profile_root / "user" / "agent_user.txt"
    if preferred.exists():
        return preferred
    return LEGACY_USER_PROMPT_PATH


def _compose_system_prompt(packet: Dict[str, object]) -> str:
    parts: List[str] = []
    for path in _system_prompt_paths(packet):
        txt = _read_optional_text(path).strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).rstrip() + "\n"


def render_prompts(packet: Dict[str, object]) -> Dict[str, str]:
    agent = dict(packet.get("agent") or {})
    own = dict(packet.get("own_state") or {})
    constraints = dict(packet.get("constraints") or {})

    geo = dict(packet.get("geo") or {})
    geo_brief = dict(geo.get("local_area_brief") or {})
    geo_text = str(geo_brief.get("summary_text") or "").strip()
    geo_lang = str(geo_brief.get("language") or agent.get("language_profile") or "")

    mapping = {
        "{{CALLSIGN}}": str(agent.get("callsign") or "UNKNOWN"),
        "{{ROLE}}": str(agent.get("role") or "unit"),
        "{{FUNCTION}}": str(agent.get("function") or "generic"),
        "{{SIDE}}": str(agent.get("side") or "blue"),
        "{{SUPERIOR}}": str(agent.get("superior") or "(ingen)"),
        "{{SUBORDINATES}}": _subordinate_names(packet),
        "{{MISSION}}": str(agent.get("mission") or ""),
        "{{LANGUAGE_PROFILE}}": str(agent.get("language_profile") or ""),
        "{{DOCTRINE_PROFILE}}": str(agent.get("doctrine_profile") or ""),
        "{{STRENGTH}}": str(own.get("strength") or ""),
        "{{AMMO}}": str(own.get("ammo") or ""),
        "{{MORALE}}": str(own.get("morale") or ""),
        "{{POSTURE}}": str(own.get("posture") or ""),
        "{{READINESS}}": str(own.get("readiness") or ""),
        "{{COMBAT_VALUE}}": str(own.get("combat_value") or ""),
        "{{DECISION_HORIZON_S}}": str(constraints.get("decision_horizon_sec") or ""),
        "{{GEO_LANGUAGE}}": geo_lang,
        "{{GEO_AREA_BRIEF}}": geo_text,
        "{{SITUATION_JSON}}": json.dumps(packet, ensure_ascii=False, indent=2),
    }

    system_prompt = _compose_system_prompt(packet)
    user_prompt_template = _read_text(_user_prompt_path(packet))
    user_prompt = _render_template(user_prompt_template, mapping)

    if "{{GEO_AREA_BRIEF}}" not in user_prompt_template:
        if geo_text:
            if str(geo_lang).lower().startswith("sv"):
                user_prompt = user_prompt.rstrip() + "\n\nTerrängbedömning i närområdet:\n" + geo_text + "\n"
            else:
                user_prompt = user_prompt.rstrip() + "\n\nLocal terrain assessment:\n" + geo_text + "\n"

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "full_prompt": system_prompt.rstrip() + "\n\n" + user_prompt.rstrip() + "\n",
    }


def write_prompt_log(agent_dir: Path, packet: Dict[str, object], raw_response: str) -> None:
    prompts = render_prompts(packet)

    (agent_dir / "last_packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (agent_dir / "last_system_prompt.txt").write_text(
        prompts["system_prompt"],
        encoding="utf-8",
    )
    (agent_dir / "last_user_prompt.txt").write_text(
        prompts["user_prompt"],
        encoding="utf-8",
    )
    (agent_dir / "last_full_prompt.txt").write_text(
        prompts["full_prompt"],
        encoding="utf-8",
    )
    (agent_dir / "last_llm_response.txt").write_text(
        raw_response,
        encoding="utf-8",
    )

    log_path = agent_dir / "llm_trace.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("SYSTEM PROMPT\n")
        f.write("-" * 80 + "\n")
        f.write(prompts["system_prompt"].rstrip() + "\n\n")
        f.write("USER PROMPT\n")
        f.write("-" * 80 + "\n")
        f.write(prompts["user_prompt"].rstrip() + "\n\n")
        f.write("RAW LLM RESPONSE\n")
        f.write("-" * 80 + "\n")
        f.write((raw_response or "").rstrip() + "\n")
