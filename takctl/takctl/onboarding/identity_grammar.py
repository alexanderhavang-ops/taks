from __future__ import annotations
from typing import Any, Dict

def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()

def _int(v: Any, default: int = 0) -> int:
    try:
        s = _s(v)
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default

# ---------------------------------------------------------------------------
# Hemvärnet team colors (Instruktion ATAK Hemvärn v0.7, avsnitt 2.3)
#
# Färgstruktur:
#   - Bataljonsstab/Ledning: Svart
#   - 1. Kompaniet: Vit
#   - 2. Kompaniet: Orange
#   - 3. Kompaniet: Rosa
#   - 4. Kompaniet: Gråblå
#   - Plutoner (inom respektive kompani):
#       1: Lila
#       2: Blå
#       3: Mörkröd
#       4: Mörkgrön
#   - Grupper/enskilda: samma färg som plutonen
#
# NOTE: ATAK expects English team names. We map Swedish -> likely ATAK strings.
# ---------------------------------------------------------------------------
def _hv_team_color(ctx: Dict[str, Any]) -> str:
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
        1: "Purple",   # Lila
        2: "Blue",     # Blå
        3: "Maroon",   # Mörkröd
        4: "Green",    # Mörkgrön
    }
    # Company colors (fallback)
    company_colors = {
        1: "White",    # Vit
        2: "Orange",   # Orange
        3: "Magenta",  # Rosa
        4: "Cyan",     # Gråblå (best-effort)
    }

    if platoon in platoon_colors:
        return platoon_colors[platoon]
    if company in company_colors:
        return company_colors[company]
    return "White"

def _hv_callsign(ctx: Dict[str, Any]) -> str:
    # Keep existing style: unit + n (policy.conf can further normalize)
    unit = _s(ctx.get("unit")) or _s(ctx.get("bn"))
    n = _s(ctx.get("n"))
    if unit and n:
        return f"{unit}{n}"
    if unit:
        return unit
    if n:
        return f"HV{n}"
    return ""

# ---------------------------------------------------------------------------
# US Army (v1 placeholder grammar)
# Make it visibly different from Hemvärnet.
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
    # If a numeric team exists, spread over common colors deterministically
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
        # allow role -> atak role type later; keep simple now
        out["atak_role_type"] = "Soldier"
        return out

    # default: hemvarnet
    out["callsign"] = _hv_callsign(ctx)
    out["team"] = _hv_team_color(ctx)
    # conservative default; can be made role-driven later
    out["atak_role_type"] = "HQ" if _s(ctx.get("battalion_role")) else None
    return out
