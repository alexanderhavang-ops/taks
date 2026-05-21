from __future__ import annotations

from typing import Any, Dict

from takctl.onboarding.fal import derive_fal_ctx


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def derive_grammar(policy_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Authoritative identity builder.

    Builds structural variants:
      - FAL      : lowest non-empty doctrinal FAL + optional <n>
                   examples: EA3 / AR2 / RQ1 / VQ
      - FALFAL   : lowest-unit-fal + broader identifier-fal + optional <n>
                   examples: EAXW1 / ARRQ2 / RQVQ1
      - FAL_TAK  : special TAK grammar <Platoon><Company><Group><Platoon><n>
                   example: AQEA1

    Then selects one based on ctx.callsign_policy (overridable):
      - FAL
      - FALFAL
      - FALSPECIAL (alias for FAL_TAK)
      - FAL_TAK

    Important:
      - Do NOT invent outward-facing extra callsign fields.
      - If policy says FAL_TAK, then callsign is the FAL_TAK variant.
      - doctrinal FAL/FALFAL come from real FAL building blocks only.
    """
    ctx = dict(ctx or {})

    pid = _s(policy_id).lower()
    if pid and pid != "hemvarnet":
        username = _s(ctx.get("username"))
        unit = _s(ctx.get("unit"))
        n = _s(ctx.get("n"))

        if unit and n:
            callsign = f"{unit}{n}"
        elif unit:
            callsign = unit
        elif username:
            callsign = username
        else:
            callsign = pid.upper()

        return {
            "callsign": callsign,
            "team": _s(ctx.get("team")) or "Blue",
            "atak_role_type": _s(ctx.get("atak_role_type")) or None,
            "callsign_policy_effective": "GENERIC",
            "callsign_variants": {
                "GENERIC": callsign,
                "FAL": "",
                "FALFAL": "",
                "FAL_TAK": ""
            },
            "callsign_structural": {
                "policy_id": pid,
                "unit": unit or None,
                "n": n or None
            },
        }

    # Use policy_cfg from ctx if caller provided it; otherwise derive best-effort only.
    policy_cfg = ctx.get("policy_cfg")

    # Structural building blocks
    d = derive_fal_ctx(policy_cfg, ctx)

    battalion_fal = _s(ctx.get("battalion_fal") or d.get("battalion_fal"))
    battalion_second = _s(d.get("battalion_second"))

    company_letter = _s(d.get("company_letter") or ctx.get("company"))
    platoon_letter = _s(d.get("platoon_letter") or ctx.get("platoon"))
    group_letter = _s(d.get("group_letter") or ctx.get("group"))

    company_fal = _s(d.get("company_fal") or d.get("company_callsign"))
    platoon_fal = _s(d.get("platoon_fal"))
    group_fal = _s(d.get("group_fal"))

    n = _s(ctx.get("n"))

    # ----------------
    # Structural variants
    # ----------------

    # FAL: lowest available real doctrinal FAL
    lowest_fal = ""
    if group_fal:
        lowest_fal = group_fal
    elif platoon_fal:
        lowest_fal = platoon_fal
    elif company_fal:
        lowest_fal = company_fal
    elif battalion_fal:
        lowest_fal = battalion_fal

    FAL = f"{lowest_fal}{n}" if lowest_fal and n else lowest_fal

    # FALFAL: lowest unit first, broader identifier second
    #
    # Preferred chains:
    #   group_fal   + company_fal    -> EAXW / EARQ / ...
    #   platoon_fal + company_fal    -> ARRQ / AQQQ? etc
    #   company_fal + battalion_fal  -> RQVQ
    #
    # We intentionally DO NOT build the old wrong company+platoon+group form.
    base_fal = ""
    identifier_fal = ""

    if group_fal and company_fal:
        base_fal = group_fal
        identifier_fal = company_fal
    elif platoon_fal and company_fal:
        base_fal = platoon_fal
        identifier_fal = company_fal
    elif company_fal and battalion_fal:
        base_fal = company_fal
        identifier_fal = battalion_fal

    FALFAL_prefix = f"{base_fal}{identifier_fal}" if base_fal and identifier_fal else ""
    FALFAL = f"{FALFAL_prefix}{n}" if FALFAL_prefix and n else FALFAL_prefix

    # FAL_TAK: Platoon Company Group Platoon
    # Structural signature: first letter == fourth letter
    FAL_TAK_prefix = ""
    if platoon_letter and company_letter and group_letter:
        FAL_TAK_prefix = f"{platoon_letter}{company_letter}{group_letter}{platoon_letter}"
    FAL_TAK = f"{FAL_TAK_prefix}{n}" if FAL_TAK_prefix and n else FAL_TAK_prefix

    variants = {
        "FAL": FAL,
        "FALFAL": FALFAL,
        "FAL_TAK": FAL_TAK,
    }

    # ----------------
    # Policy selection
    # ----------------
    raw = _s(ctx.get("callsign_policy")).upper()
    if raw in ("FALSPECIAL", "FAL-TAK", "FAL_TAK"):
        effective = "FAL_TAK"
    elif raw == "FALFAL":
        effective = "FALFAL"
    elif raw == "FAL":
        effective = "FAL"
    else:
        effective = "FALFAL"

    callsign = variants.get(effective, "") or ""
    if not callsign:
        raise RuntimeError("Unable to derive callsign from provided structure")

    return {
        "callsign": callsign,
        "team": _s(ctx.get("team")) or "Blue",
        "atak_role_type": _s(ctx.get("atak_role_type")) or None,
        "callsign_policy_effective": effective,
        "callsign_variants": variants,
        "callsign_structural": {
            "battalion_fal": battalion_fal or None,
            "battalion_second": battalion_second or None,
            "company_letter": company_letter or None,
            "platoon_letter": platoon_letter or None,
            "group_letter": group_letter or None,
            "company_fal": company_fal or None,
            "platoon_fal": platoon_fal or None,
            "group_fal": group_fal or None,
            "base_fal": base_fal or None,
            "identifier_fal": identifier_fal or None,
        },
    }
