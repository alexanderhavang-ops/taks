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
    # company + battalion-second: QW, RW, SW, TW
    return [f"{c}{battalion_second}" for c in _COMPANY_LETTERS]


def _platoon_fals(company_fal: str) -> list[str]:
    # platoon + company: AQ, BQ, CQ, DQ, EQ under QW
    company_fal = _upper(company_fal)
    company_letter = company_fal[:1]
    return [f"{p}{company_letter}" for p in _PLATOON_LETTERS]


def _group_fals(platoon_fal: str) -> list[str]:
    # group + platoon: EA, FA, GA, HA under AQ
    platoon_fal = _upper(platoon_fal)
    platoon_letter = platoon_fal[:1]
    return [f"{g}{platoon_letter}" for g in _GROUP_PREFIXES]


def _group_channel_fal(company_fal: str, group_fal: str) -> str:
    # Gruppscope skrivs grupp först, sedan kompani: EA + PQ => EAPQ
    return f"{_upper(group_fal)}{_upper(company_fal)}"


def _seed_channels_from_ctx(derived: dict[str, Any]) -> list[str]:
    battalion_fal = _upper(derived.get("battalion_fal"))
    company_fal = _upper(derived.get("company_fal"))
    platoon_fal = _upper(derived.get("platoon_fal"))
    group_fal = _upper(derived.get("group_fal"))

    n_raw = _s(derived.get("n"))
    try:
        n = int(n_raw) if n_raw else None
    except Exception:
        n = None

    battalion_channel = f"BatL-{battalion_fal}" if battalion_fal else ""
    company_channel = f"KompL-{company_fal}" if company_fal else ""
    platoon_channel = f"PlutL-{platoon_fal}" if platoon_fal else ""
    group_channel = f"GruppL-{_group_channel_fal(company_fal, group_fal)}" if company_fal and group_fal else ""

    seeds: list[str] = []

    # Ledningspluton / P-kompani: stab-/ledningspluton + bataljon.
    # P-kompani ska inte använda vanlig pluton-FAL som AP/BP här.
    # För 46/VQ blir stab-/ledningsplutonens talkanal PlutL-PQ.
    # Detta ska gälla även om identiteten råkar bära gruppprefix, t.ex. EAPQ1.
    if company_fal.startswith("P"):
        battalion_second = battalion_fal[1:2] if len(battalion_fal) >= 2 else ""
        staff_platoon_channel = f"PlutL-P{battalion_second}" if battalion_second else ""
        if staff_platoon_channel and battalion_channel:
            seeds.extend([staff_platoon_channel, battalion_channel])
        elif staff_platoon_channel:
            seeds.append(staff_platoon_channel)
        elif battalion_channel:
            seeds.append(battalion_channel)
        return _uniq(seeds)

    # Gruppmedlem: bara grupp. Gruppchef + stf: grupp + pluton.
    if group_channel:
        if n in (1, 2):
            seeds.append(group_channel)
            if platoon_channel:
                seeds.append(platoon_channel)
        else:
            seeds.append(group_channel)
        return _uniq(seeds)

    # E-pluton / stab- och sambandgrupp: kompani + bataljon.
    if platoon_fal.startswith("E") and company_channel and battalion_channel:
        seeds.extend([company_channel, battalion_channel])
        return _uniq(seeds)

    # Plutonchef, stf, signalist: pluton + kompani.
    if platoon_channel:
        if n in (1, 2, 3) and company_channel:
            seeds.extend([platoon_channel, company_channel])
        else:
            seeds.append(platoon_channel)
        return _uniq(seeds)

    # Kompaniledning: kompani + bataljon.
    if company_channel and battalion_channel:
        seeds.extend([company_channel, battalion_channel])
        return _uniq(seeds)

    # Batstab: bara bataljon.
    if battalion_channel:
        seeds.append(battalion_channel)

    return _uniq(seeds)


def derive_voice_topology(policy_cfg, ctx: dict[str, Any] | None) -> dict[str, Any]:
    """
    Voice topology for the current policy.

    Hemvärnet:
      BatL-$BATALIONFAL
      PlutL-P$BATTALION_SECOND
      KompL-$COMPANYFAL
      PlutL-$PLATOONFAL
      GruppL-$COMPANYFAL$GROUPFAL

    Other policies:
      simple generic flat channel set based on unit name only
    """
    base_ctx = dict(ctx or {})

    policy_id = _s(base_ctx.get("policy_id")).lower()
    if not policy_id:
        try:
            if "meta" in policy_cfg:
                meta = policy_cfg["meta"]
                policy_id = _s(meta.get("id") or meta.get("policy_id")).lower()
        except Exception:
            policy_id = ""

    if policy_id and policy_id != "hemvarnet":
        unit_label = _unit_label(base_ctx, None)
        channels = _uniq([
            f"Org-{unit_label}",
            "Ledning",
            "Samverkan",
        ])
        return {
            "policy_family": policy_id,
            "render_mode": "flat",
            "mission_label": f"Radio-{unit_label}",
            "unit": unit_label,
            "channels": channels,
            "relations": {
                ch: {
                    "kind": "generic",
                    "logical_parent": None,
                } for ch in channels
            },
            "seed_channels": channels[:2],
            "channel_count": len(channels),
        }
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
        if n not in relations:
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
                group_scope_fal = _group_channel_fal(company_fal, group_fal)
                group_channel = f"GruppL-{group_scope_fal}"
                add_channel(
                    group_channel,
                    {
                        "kind": "group",
                        "fal": group_scope_fal,
                        "group_scope_fal": group_scope_fal,
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
