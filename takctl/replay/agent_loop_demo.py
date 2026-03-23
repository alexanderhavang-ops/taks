from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from llm_decision import build_agent_packet, parse_and_validate
from tasking import decision_to_work

SAMPLE_RESPONSE = Path("/opt/taks/takctl/replay/sample_attq_response.json")


def build_demo_packet(sim_time_s: int) -> Dict[str, Any]:
    return build_agent_packet(
        sim_time_s=sim_time_s,
        agent={
            "callsign": "ATTQ",
            "role": "platoon",
            "side": "blue",
            "superior": "TQ",
            "mission": "Fördröj fiendens framträngande öster om Ystad",
            "control_mode": "llm",
        },
        own_state={
            "position": {"lat": 55.4220, "lon": 13.9180},
            "strength": 24,
            "ammo": "tillräcklig",
            "morale": "stabil",
            "posture": "screening",
            "readiness": "marschberedskap 60",
            "combat_value": "god",
        },
        subordinates=[
            {"callsign": "EATQ", "status": "ok"},
            {"callsign": "FATQ", "status": "ok"},
            {"callsign": "GATQ", "status": "no_recent_report"},
        ],
        observations=[
            {
                "type": "enemy_naval_contact",
                "age_sec": 120,
                "location": {"lat": 55.410, "lon": 13.950},
                "confidence": 0.8,
                "description": "1 landstigningsfartyg, 1 eskort",
            }
        ],
        friendly_reports=[
            {
                "from": "SQ",
                "age_sec": 180,
                "text": "Försvar av Ystads hamn påbörjat.",
                "kind": "status_report",
                "meta": {},
                "sim_time_s": sim_time_s - 180,
            }
        ],
        constraints={
            "roe": "defensiv",
            "decision_horizon_sec": 300,
        },
    )


def main() -> None:
    sim_time_s = 2100
    packet = build_demo_packet(sim_time_s)

    raw_text = SAMPLE_RESPONSE.read_text(encoding="utf-8")
    result = parse_and_validate(raw_text, packet)

    work = decision_to_work(
        agent_callsign="ATTQ",
        superior_callsign="TQ",
        decision=result.decision,
        sim_time_s=sim_time_s,
        has_subordinates=True,
        decision_horizon_s=300,
    )

    print("DECISION")
    print(json.dumps(result.decision, ensure_ascii=False, indent=2))
    print()
    print("WORK")
    print(json.dumps(work, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
