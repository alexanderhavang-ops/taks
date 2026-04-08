from __future__ import annotations

from typing import Any

from takctl.onboarding.fal import battalion_no_from_unit, derive_fal_ctx


_COMPANY_LETTERS = ["Q", "R", "S", "T"]
_PLATOON_LETTERS = ["A", "B", "C", "D", "E"]
_GROUP_PREFIXES = ["E", "F", "G", "H"]


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _upper(v: Any) -> str:
    return _s(v).upper()


def _unit_label(ctx: dict[str, Any], battalion_no: int | None) -> str:
    unit = _s(ctx.get("unit"))
    if unit:
        return unit
    if battalion_no:
        return f"{battalion_no}hvbat"
    return "unknown-unit"


def _uniq(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = _s(item)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _company_fals(battalion_second: str) -> list[str]:
    return [f"{c}{battalion_second}" for c in _COMPANY_LETTERS]


def _platoon_fals(company_fal: str) -> list[str]:
    company_fal = _upper(company_fal)
    company_letter = company_fal[:1]
    return [f"{company_letter}{p}" for p in _PLATOON_LETTERS]


def _group_fals(platoon_fal: str) -> list[str]:
    platoon_fal = _upper(platoon_fal)
    platoon_letter = platoon_fal[1:2]
    return [f"{g}{platoon_letter}" for g in _GROUP_PREFIXES]


def _seed_channels_from_ctx(derived: dict[str, Any]) -> list[str]:
    battalion_fal = _upper(derived.get("battalion_fal"))
    battalion_second = battalion_fal[1:2] if len(battalion_fal) >= 2 else ""
    company_fal = _upper(derived.get("company_fal"))
    platoon_fal = _upper(derived.get("platoon_fal"))
    group_fal = _upper(derived.get("group_fal"))

    seeds: list[str] = []

    if group_fal and platoon_fal:
        seeds.extend([f"GruppL-{group_fal}", f"PlutL-{platoon_fal}"])
    elif platoon_fal and company_fal:
        seeds.extend([f"PlutL-{platoon_fal}", f"KompL-{company_fal}"])
    elif company_fal and battalion_fal:
        seeds.extend([f"KompL-{company_fal}", f"BatL-{battalion_fal}"])
    elif battalion_fal and battalion_second:
        seeds.extend([f"BatL-{battalion_fal}", f"PlutL-P{battalion_second}"])

    return _uniq(seeds)


def derive_voice_topology(policy_cfg, ctx: dict[str, Any] | None) -> dict[str, Any]:
    """
    Hemvärnet battalion voice topology, rendered as a FLAT list for Mumble.

    Logical model:
      BatL-$BATALIONFAL
      PlutL-P$BATTALION_SECOND
      KompL-$COMPANYFAL
      PlutL-$PLATOONFAL
      GruppL-$GROUPFAL

    Example for 48hvbat / VW:
      BatL-VW
      PlutL-PW
      KompL-QW, KompL-RW, KompL-SW, KompL-TW
      PlutL-QA ... PlutL-QE, ...
      GruppL-EA ... GruppL-HE, ...
    """
    base_ctx = dict(ctx or {})
    derived = derive_fal_ctx(policy_cfg, base_ctx)
    merged = dict(base_ctx)
    merged.update(derived)

    battalion_fal = _upper(merged.get("battalion_fal"))
    battalion_no = merged.get("battalion_no")
    if battalion_no is None:
        battalion_no = battalion_no_from_unit(_s(merged.get("unit")))

    if not battalion_fal or len(battalion_fal) < 2:
        raise RuntimeError("derive_voice_topology requires battalion_fal (e.g. VW)")

    battalion_second = battalion_fal[1:2]
    unit_label = _unit_label(merged, battalion_no)
    mission_label = f"Samband-{unit_label}"

    battalion_channel = f"BatL-{battalion_fal}"
    staff_platoon_fal = f"P{battalion_second}"
    staff_platoon_channel = f"PlutL-{staff_platoon_fal}"

    channels: list[str] = []
    relations: dict[str, dict[str, Any]] = {}

    def add_channel(name: str, meta: dict[str, Any]) -> None:
        n = _s(name)
        if not n:
            return
        if n not in channels:
            channels.append(n)
        relations[n] = dict(meta)

    add_channel(
        battalion_channel,
        {
            "kind": "battalion",
            "fal": battalion_fal,
            "battalion_fal": battalion_fal,
            "logical_parent": None,
        },
    )
    add_channel(
        staff_platoon_channel,
        {
            "kind": "staff_platoon",
            "fal": staff_platoon_fal,
            "battalion_fal": battalion_fal,
            "logical_parent": battalion_channel,
        },
    )

    companies: list[dict[str, Any]] = []
    for company_fal in _company_fals(battalion_second):
        company_channel = f"KompL-{company_fal}"
        add_channel(
            company_channel,
            {
                "kind": "company",
                "fal": company_fal,
                "company_fal": company_fal,
                "battalion_fal": battalion_fal,
                "logical_parent": battalion_channel,
            },
        )

        platoons: list[dict[str, Any]] = []
        for platoon_fal in _platoon_fals(company_fal):
            platoon_channel = f"PlutL-{platoon_fal}"
            add_channel(
                platoon_channel,
                {
                    "kind": "platoon",
                    "fal": platoon_fal,
                    "platoon_fal": platoon_fal,
                    "company_fal": company_fal,
                    "battalion_fal": battalion_fal,
                    "logical_parent": company_channel,
                },
            )

            groups: list[str] = []
            for group_fal in _group_fals(platoon_fal):
                group_channel = f"GruppL-{group_fal}"
                add_channel(
                    group_channel,
                    {
                        "kind": "group",
                        "fal": group_fal,
                        "group_fal": group_fal,
                        "platoon_fal": platoon_fal,
                        "company_fal": company_fal,
                        "battalion_fal": battalion_fal,
                        "logical_parent": platoon_channel,
                    },
                )
                groups.append(group_channel)

            platoons.append(
                {
                    "channel": platoon_channel,
                    "platoon_fal": platoon_fal,
                    "groups": groups,
                }
            )

        companies.append(
            {
                "channel": company_channel,
                "company_fal": company_fal,
                "platoons": platoons,
            }
        )

    seed_channels = _seed_channels_from_ctx(merged)

    return {
        "policy_family": "hemvarnet",
        "render_mode": "flat",
        "mission_label": mission_label,
        "unit": unit_label,
        "battalion_no": battalion_no,
        "battalion_fal": battalion_fal,
        "battalion_channel": battalion_channel,
        "staff_platoon_channel": staff_platoon_channel,
        "companies": companies,
        "channels": channels,
        "relations": relations,
        "seed_channels": seed_channels,
        "channel_count": len(channels),
    }
