from __future__ import annotations
# TAKS_DEBUG_SIGNATURE_20260227: append Z9SIG to hemvarnet callsign (source->runtime sync proof)
from typing import Any, Dict

from takctl.onboarding.fal import derive_fal_ctx


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _upper(v: Any) -> str:
    return _s(v).upper()


def _int(v: Any, default: int = 0) -> int:
    try:
        s = _s(v)
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Hemvärnet team colors (keep for now; we can adjust once your UI is final)
# NOTE: ATAK expects English team names for locationTeam.
# ---------------------------------------------------------------------------
def _hv_team_color(ctx: Dict[str, Any]) -> str:
    # Prefer explicit selection if provided (UI uses Lagfärg select)
    team = _s(ctx.get("team"))
    if team:
        return team

    role = _s(ctx.get("role")).lower()
    batt_role = _s(ctx.get("battalion_role")).lower()

    # Treat these as "ledning/stab"
    if batt_role in ("ledning", "stab", "bataljonsstab", "hq", "staff", "command"):
        return "Black"
    if role in ("ledning", "stab", "bataljonsstab", "hq", "staff", "command", "s1", "s2", "s3", "s4", "stric"):
        return "Black"

    company = _int(ctx.get("company"), 0)
    platoon = _int(ctx.get("platoon"), 0)

    # Platoon colors (preferred when known)
    platoon_colors = {
        1: "Purple",
        2: "Blue",
        3: "Maroon",
        4: "Green",
    }
    # Company colors (fallback)
    company_colors = {
        1: "White",
        2: "Orange",
        3: "Magenta",
        4: "Cyan",
    }

    if platoon in platoon_colors:
        return platoon_colors[platoon]
    if company in company_colors:
        return company_colors[company]
    return "Blue"


def _hv_callsign(ctx: Dict[str, Any], policy_cfg=None) -> str:
    """
    Hemvärnet callsign model (as you described):
      - battalion: VQ      (+1 leader if needed)
      - company:   RQ/SQ/TQ  (company letter + battalion 2nd letter)
      - platoon:   BS        (platoon letter + company letter)
      - group:     BSFB      (platoon + group letter + platoon letter)
      - individual: <base><n>  e.g. BSFB7
    """
    # enrich ctx with derived FAL + letters + building blocks
    d = derive_fal_ctx(policy_cfg, dict(ctx or {}))
    battalion_fal = _upper(ctx.get("battalion_fal") or d.get("battalion_fal"))
    company_callsign = _upper(d.get("company_callsign"))
    platoon_callsign = _upper(d.get("platoon_callsign"))
    group_callsign = _upper(d.get("group_callsign"))

    n = _s(ctx.get("n"))

    # choose the best "base" available
    base = ""
    if group_callsign:
        base = group_callsign
    elif platoon_callsign:
        base = platoon_callsign
    elif company_callsign:
        base = company_callsign
    elif battalion_fal:
        base = battalion_fal

    # If no base, last-resort: just n (but try hard not to land here)
    if base and n:
        return f"{base}{n}"
    if base:
        return base
    if n:
        return n
    return ""


# ---------------------------------------------------------------------------
# US Army (placeholder)
# ---------------------------------------------------------------------------
def _us_company_name(ctx: Dict[str, Any]) -> str:
    c = _s(ctx.get("company")) or _s(ctx.get("company_letter"))
    if len(c) == 1 and c.isalpha():
        return {"a": "ALPHA", "b": "BRAVO", "c": "CHARLIE", "d": "DELTA"}.get(c.lower(), c.upper())
    return c.upper() if c else "ALPHA"


def _us_callsign(ctx: Dict[str, Any]) -> str:
    comp = _us_company_name(ctx)
    squad = _int(ctx.get("squad"), 0) or _int(ctx.get("platoon"), 0)
    team = _int(ctx.get("team"), 0)
    n = _int(ctx.get("n"), 0)

    if squad and team:
        suffix = f"{squad}{team}"
    elif squad:
        suffix = f"{squad}"
    elif n:
        suffix = f"{n}"
    else:
        suffix = "1"
    return f"{comp}-{suffix}"


def _us_team(ctx: Dict[str, Any]) -> str:
    team = _int(ctx.get("team"), 0) or _int(ctx.get("n"), 0)
    colors = ["Red", "Blue", "Green", "Yellow", "Orange", "Purple", "White", "Black"]
    if team > 0:
        return colors[(team - 1) % len(colors)]
    return "Red"


def derive(policy_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    pid = (_s(policy_id) or "hemvarnet").lower()
    out: Dict[str, Any] = {}

    if pid == "us_army":
        out["callsign"] = _us_callsign(ctx)
        out["team"] = _us_team(ctx)
        out["atak_role_type"] = "Soldier"
        return out

    # default: hemvarnet
    out["callsign"] = _hv_callsign(ctx, policy_cfg=None)  + "Z9SIG"# policy_cfg injected at Policy layer via ctx enrichment anyway
    out["team"] = _hv_team_color(ctx)
    out["atak_role_type"] = _s(ctx.get("atak_role_type")) or None
    return out


def derive_grammar(policy_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    return derive(policy_id, ctx)
