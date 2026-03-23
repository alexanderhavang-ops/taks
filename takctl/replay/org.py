from __future__ import annotations

from typing import Any, Dict

from takctl.onboarding.fal import derive_fal_ctx


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _upper(v: Any) -> str:
    return _s(v).upper()


def infer_company_from_callsign(callsign: str, battalion_fal: str) -> str:
    """
    Best-effort replay helper.

    Examples with battalion_fal=VQ:
      AQ -> QQ
      BQ -> QQ
      AR -> RQ
      AT -> TQ

    For full company callsigns like QQ/RQ/SQ/TQ, returns as-is.
    For group/person callsigns like EAQQ / EAQQ1, returns QQ.
    """
    cs = _upper(callsign)
    bf = _upper(battalion_fal)

    if len(bf) < 2:
        return ""

    batt_second = bf[1]

    # Full company callsign already, e.g. PQ / QQ / RQ / SQ / TQ
    if len(cs) == 2 and cs[0] in {"P", "Q", "R", "S", "T", "X", "N", "U", "W"} and cs[1] == batt_second:
        return cs

    # Platoon callsign, e.g. AQ / AR / AT  -> company is 2nd letter + battalion second
    if len(cs) == 2 and cs[0].isalpha() and cs[1].isalpha():
        platoon_letter = cs[0]
        company_letter = cs[1]
        return f"{company_letter}{batt_second}"

    # Group/unit/person shapes that end with company callsign, e.g. EAQQ / EAQQ1
    if len(cs) >= 4:
        tail4 = cs[-4:]
        if len(tail4) == 4 and tail4[2:].isalpha() and tail4[3] == batt_second:
            return tail4[2:]

    if len(cs) >= 5 and cs[-1].isdigit():
        tail4 = cs[-5:-1]
        if len(tail4) == 4 and tail4[2:].isalpha() and tail4[3] == batt_second:
            return tail4[2:]

    return ""


def build_replay_fal_ctx(callsign: str, battalion_fal: str) -> Dict[str, Any]:
    """
    Small replay-facing helper using doctrinal derivation where possible.
    """
    cs = _upper(callsign)
    bf = _upper(battalion_fal)

    out: Dict[str, Any] = {
        "callsign": cs,
        "battalion_fal": bf,
        "company_callsign": infer_company_from_callsign(cs, bf),
    }

    # For platoon callsigns like AQ/AR/AT, enrich via derive_fal_ctx
    if len(cs) == 2 and cs[0].isalpha() and cs[1].isalpha() and len(bf) == 2:
        derived = derive_fal_ctx(
            None,
            {
                "battalion_fal": bf,
                "company": cs[1],
                "platoon": cs[0],
            },
        )
        if derived.get("company_callsign"):
            out["company_callsign"] = str(derived["company_callsign"])
        if derived.get("company_letter"):
            out["company_letter"] = str(derived["company_letter"])
        if derived.get("platoon_letter"):
            out["platoon_letter"] = str(derived["platoon_letter"])

    return out
