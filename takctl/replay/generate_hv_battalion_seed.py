from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SEED_DIR = Path("/opt/tak/tools/takctl/replay/seeds/ystad_001")
OUT_PATH = SEED_DIR / "forces.generated.json"

COMPANIES = ["Q", "R", "S", "T"]
PLATOONS = ["A", "B", "C", "D", "E"]
GROUPS = ["E", "F", "G", "H"]

DEFAULTS = {
    "battalion_strength": 40,          # bataljonsstab + ledningspluton
    "company_staff_tross_strength": 20,
    "group_strength": 8,
    "readiness_default": "marschberedskap 600",
    "combat_value_default": "god",
}

READINESS_OVERRIDES = {
    "VQ": "marschberedskap 600",
    "QQ": "marschberedskap 60",
    "AQ": "marschberedskap 15",
}

# Revinge-ish samlingsplats; små offsetar för att undvika exakt samma punkt
BASE_LAT = 55.7060
BASE_LON = 13.4720


def pos_with_offset(lat: float, lon: float, east_idx: int, north_idx: int) -> Dict[str, float]:
    return {
        "lat": round(lat + north_idx * 0.0020, 6),
        "lon": round(lon + east_idx * 0.0030, 6),
    }


def battalion_second_letter(battalion_fal: str) -> str:
    return battalion_fal[1]


def company_fal(company_letter: str, battalion_fal: str) -> str:
    return f"{company_letter}{battalion_second_letter(battalion_fal)}"


def platoon_fal(platoon_letter: str, company_letter: str) -> str:
    return f"{platoon_letter}{company_letter}"


def group_fal(group_letter: str, platoon_letter: str) -> str:
    return f"{group_letter}{platoon_letter}"


def group_falfal(group_letter: str, platoon_letter: str, company_fal_value: str) -> str:
    return f"{group_fal(group_letter, platoon_letter)}{company_fal_value}"


def soldier_callsign(group_falfal_value: str, n: int) -> str:
    return f"{group_falfal_value}{n}"


def mobility_for_platoon(platoon_letter: str, company_type: str) -> Dict[str, Any]:
    if platoon_letter == "A":
        return {
            "type": "bandvagn",
            "speed_kph_max": 50,
            "terrain_mobility": "good",
        }
    if platoon_letter in {"B", "C", "D"}:
        if company_type == "bevakning":
            return {
                "type": "external_bus_transport",
                "speed_kph_max": 90,
                "terrain_mobility": "poor",
            }
        return {
            "type": "pb8_sprinter_trailer",
            "speed_kph_max": 90,
            "terrain_mobility": "poor",
            "vehicles_per_group": 1,
        }
    return {
        "type": "30_bil",
        "speed_kph_max": 80,
        "terrain_mobility": "medium",
    }


def readiness_for(name: str) -> str:
    return READINESS_OVERRIDES.get(name, DEFAULTS["readiness_default"])


def make_unit(
    *,
    callsign: str,
    role: str,
    parent: str | None,
    position: Dict[str, float],
    strength: int,
    readiness: str,
    combat_value: str,
    mobility: Dict[str, Any],
    language_profile: str = "sv-se-military",
    doctrine_profile: str = "swedish-home-guard",
) -> Dict[str, Any]:
    return {
        "callsign": callsign,
        "role": role,
        "parent": parent,
        "position": position,
        "strength": strength,
        "readiness": readiness,
        "combat_value": combat_value,
        "language_profile": language_profile,
        "doctrine_profile": doctrine_profile,
        "mobility": mobility,
    }


def main() -> None:
    battalion_fal = "VQ"
    blue_units: List[Dict[str, Any]] = []

    blue_units.append(
        make_unit(
            callsign=battalion_fal,
            role="battalion",
            parent=None,
            position=pos_with_offset(BASE_LAT, BASE_LON, 0, 0),
            strength=DEFAULTS["battalion_strength"],
            readiness=readiness_for(battalion_fal),
            combat_value=DEFAULTS["combat_value_default"],
            mobility={"type": "mixed", "speed_kph_max": 80},
        )
    )

    pq = company_fal("P", battalion_fal)
    blue_units.append(
        make_unit(
            callsign=pq,
            role="company",
            parent=battalion_fal,
            position=pos_with_offset(BASE_LAT, BASE_LON, -1, 1),
            strength=DEFAULTS["battalion_strength"],
            readiness=readiness_for(pq),
            combat_value=DEFAULTS["combat_value_default"],
            mobility={"type": "staff_command", "speed_kph_max": 80},
        )
    )

    for ci, comp_letter in enumerate(COMPANIES, start=1):
        comp = company_fal(comp_letter, battalion_fal)
        company_type = "insats"
        blue_units.append(
            make_unit(
                callsign=comp,
                role="company",
                parent=battalion_fal,
                position=pos_with_offset(BASE_LAT, BASE_LON, ci, 0),
                strength=0,
                readiness=readiness_for(comp),
                combat_value=DEFAULTS["combat_value_default"],
                mobility={"type": company_type, "speed_kph_max": 90},
            )
        )

        company_strength = 0

        for pi, platoon_letter in enumerate(PLATOONS, start=1):
            pl = platoon_fal(platoon_letter, comp_letter)
            platoon_role = "staff_tross_platoon" if platoon_letter == "E" else "platoon"
            pl_strength = DEFAULTS["company_staff_tross_strength"] if platoon_letter == "E" else DEFAULTS["group_strength"] * len(GROUPS)

            blue_units.append(
                make_unit(
                    callsign=pl,
                    role=platoon_role,
                    parent=comp,
                    position=pos_with_offset(BASE_LAT, BASE_LON, ci, pi),
                    strength=pl_strength,
                    readiness=readiness_for(pl),
                    combat_value=DEFAULTS["combat_value_default"],
                    mobility=mobility_for_platoon(platoon_letter, company_type),
                )
            )
            company_strength += pl_strength

            if platoon_letter != "E":
                for gi, group_letter in enumerate(GROUPS, start=1):
                    gf = group_falfal(group_letter, platoon_letter, comp)
                    blue_units.append(
                        make_unit(
                            callsign=gf,
                            role="group",
                            parent=pl,
                            position=pos_with_offset(BASE_LAT, BASE_LON, ci + gi, pi),
                            strength=DEFAULTS["group_strength"],
                            readiness=readiness_for(gf),
                            combat_value=DEFAULTS["combat_value_default"],
                            mobility=mobility_for_platoon(platoon_letter, company_type),
                        )
                    )

                    for n in range(1, DEFAULTS["group_strength"] + 1):
                        sc = soldier_callsign(gf, n)
                        soldier_role = "group_leader" if n == 1 else ("assistant_group_leader" if n == 2 else "soldier")
                        blue_units.append(
                            make_unit(
                                callsign=sc,
                                role=soldier_role,
                                parent=gf,
                                position=pos_with_offset(BASE_LAT, BASE_LON, ci + gi, pi),
                                strength=1,
                                readiness=readiness_for(sc),
                                combat_value=DEFAULTS["combat_value_default"],
                                mobility=mobility_for_platoon(platoon_letter, company_type),
                            )
                        )

        for u in blue_units:
            if u["callsign"] == comp:
                u["strength"] = company_strength
                break

    red_units = [
        make_unit(
            callsign="RU-BALTIC-TF",
            role="task_force",
            parent=None,
            position={"lat": 55.3900, "lon": 14.0400},
            strength=200,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 22},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-LDG-1",
            role="landing_ship",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4050, "lon": 13.9900},
            strength=60,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 18},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-LDG-2",
            role="landing_ship",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4070, "lon": 13.9950},
            strength=60,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 18},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-LDG-3",
            role="landing_ship",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4090, "lon": 14.0000},
            strength=60,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 18},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-LDG-4",
            role="landing_ship",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4110, "lon": 14.0050},
            strength=60,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 18},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-ESC-1",
            role="escort_ship",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4080, "lon": 14.0000},
            strength=30,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "naval", "speed_kph_max": 20},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-SPETSNAZ-1",
            role="spetsnaz_group",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4010, "lon": 13.9800},
            strength=8,
            readiness="offensiv beredskap",
            combat_value="god",
            mobility={"type": "fast_rhib", "speed_kph_max": 45},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
        make_unit(
            callsign="RU-UAS-SWARM-1",
            role="uas_swarm",
            parent="RU-BALTIC-TF",
            position={"lat": 55.4000, "lon": 14.0100},
            strength=12,
            readiness="aktiv",
            combat_value="god",
            mobility={"type": "uas", "speed_kph_max": 70},
            language_profile="ru-military",
            doctrine_profile="russian-amphibious",
        ),
    ]

    out = {
        "blue": {
            "top_unit": battalion_fal,
            "language_profile": "sv-se-military",
            "doctrine_profile": "swedish-home-guard",
            "units": blue_units,
        },
        "red": {
            "top_unit": "RU-BALTIC-TF",
            "language_profile": "ru-military",
            "doctrine_profile": "russian-amphibious",
            "units": red_units,
        },
    }

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"WROTE {OUT_PATH}")
    print(f"BLUE_UNITS {len(blue_units)}")
    print(f"RED_UNITS {len(red_units)}")


if __name__ == "__main__":
    main()
