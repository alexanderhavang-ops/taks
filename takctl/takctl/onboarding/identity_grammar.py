from __future__ import annotations

from typing import Any, Dict

from takctl.onboarding.fal import derive_fal_ctx


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def derive_grammar(policy_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Authoritative identity builder.

    Builds structural variants:
      - FAL      : lowest-non-empty pair (EA/AQ/QQ/VQ) + optional <n>
      - FALFAL   : <company_callsign><platoon_letter><group_letter><n>   (doctrinal)
      - FAL_TAK  : <group_callsign><n>  (your internal TAK-friendly structure)

    Then selects one based on ctx.callsign_policy (overridable):
      - FAL
      - FALFAL
      - FALSPECIAL (alias for FAL_TAK)
      - FAL_TAK
    """
    ctx = dict(ctx or {})

    # Enrich structural building blocks (non-destructive in caller; here we just compute)
    d = derive_fal_ctx(None, ctx)

    battalion_fal = _s(ctx.get("battalion_fal") or d.get("battalion_fal"))
    company_callsign = _s(d.get("company_callsign"))   # e.g. QQ (company Q + battalion 2nd letter)
    platoon_letter = _s(d.get("platoon_letter"))       # e.g. A
    group_letter = _s(d.get("group_letter"))           # e.g. E
    group_callsign = _s(d.get("group_callsign"))       # e.g. AQEA (TAK-style)
    n = _s(ctx.get("n"))

    # ----------------
    # Structural variants
    # ----------------

    # KISS FAL:
    # - Person: two lowest non-empty "units" (group+platoon OR platoon+company OR company+battalion-suffix OR battalion) + n
    # - Unit:   same prefix but WITHOUT n (supports onboarding e.g. VQ, QQ, AQ, EA)
    company_letter = _s(d.get("company_letter") or ctx.get("company") or (company_callsign[:1] if company_callsign else ""))
    prefix = ""
    if group_letter and platoon_letter:
        prefix = f"{group_letter}{platoon_letter}"          # EA  (group leader scope)
    elif platoon_letter and company_letter:
        prefix = f"{platoon_letter}{company_letter}"        # AQ  (platoon leader scope)
    elif company_callsign:
        prefix = company_callsign                           # QQ  (company leader scope)
    elif battalion_fal:
        prefix = battalion_fal                              # VQ  (battalion leader scope)

    FAL = (f"{prefix}{n}" if n else prefix) if prefix else ""

    # Doctrinal: company scope + platoon + group + individual
    # Example: QQAE1
    FALFAL = ""
    if company_callsign and n:
        FALFAL = company_callsign
        if platoon_letter:
            FALFAL += platoon_letter
        if group_letter:
            FALFAL += group_letter
        FALFAL += n

    # Internal TAK-friendly: group_callsign already encodes platoon/company/group/platoon (AQEA)
    FAL_TAK = f"{group_callsign}{n}" if group_callsign and n else ""

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
    else:
        effective = "FAL"

    callsign = variants.get(effective, "") or ""

    if not callsign:
        raise RuntimeError("Unable to derive callsign from provided structure")

    return {
        "callsign": callsign,
        "team": _s(ctx.get("team")) or "Blue",
        "atak_role_type": _s(ctx.get("atak_role_type")) or None,
        "callsign_policy_effective": effective,
        "callsign_variants": variants,
    }
