from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _upper(v: Any) -> str:
    return _s(v).upper()


def _int(v: Any, default: int = 0) -> int:
    try:
        s = _s(v)
        return default if not s else int(float(s))
    except Exception:
        return default


def battalion_no_from_unit(unit: str) -> Optional[int]:
    """
    Best-effort: "46HV" -> 46
    """
    u = _upper(unit)
    if u.endswith("HV") and len(u) >= 4:
        prefix = u[:-2]
        try:
            return int(prefix)
        except Exception:
            return None
    return None


# -----------------------------
# Hemvärn letter helpers
# -----------------------------
_COMPANY_NUM_TO_LET = {1: "Q", 2: "R", 3: "S", 4: "T"}
_PLATOON_NUM_TO_LET = {1: "A", 2: "B", 3: "C", 4: "D"}
_GROUP_NUM_TO_LET = {1: "E", 2: "F", 3: "G", 4: "H"}


def company_letter(company: Any) -> str:
    """
    Accept either:
      - numeric 1..4
      - letter Q/R/S/T
    """
    c = _upper(company)
    if len(c) == 1 and c in ("Q", "R", "S", "T"):
        return c
    n = _int(company, 0)
    return _COMPANY_NUM_TO_LET.get(n, "")


def platoon_letter(platoon: Any) -> str:
    """
    Accept either:
      - numeric 1..4
      - letter A/B/C/D
    """
    p = _upper(platoon)
    if len(p) == 1 and p in ("A", "B", "C", "D"):
        return p
    n = _int(platoon, 0)
    return _PLATOON_NUM_TO_LET.get(n, "")


def group_letter(group: Any) -> str:
    """
    Accept either:
      - numeric 1..4
      - letter E/F/G/H
    """
    g = _upper(group)
    if len(g) == 1 and g in ("E", "F", "G", "H"):
        return g
    n = _int(group, 0)
    return _GROUP_NUM_TO_LET.get(n, "")


def _policy_fal_map(policy_cfg) -> Dict[int, str]:
    """
    Read [fal.hvbat] from policy.conf:
      46=VQ etc
    """
    out: Dict[int, str] = {}
    try:
        if policy_cfg is not None and policy_cfg.has_section("fal.hvbat"):
            sec = policy_cfg["fal.hvbat"]
            for k, v in sec.items():
                try:
                    bn = int(str(k).strip())
                except Exception:
                    continue
                vv = _upper(v)
                if len(vv) >= 2:
                    out[bn] = vv[:2]
    except Exception:
        return {}
    return out


def derive_fal_ctx(policy_cfg, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add derived keys to ctx (non-destructive). This is *context enrichment*.

    Inputs supported:
      - battalion_no (e.g. 46) OR battalion (e.g. "46") OR unit ("46HV")
      - battalion_fal (e.g. "VQ")  (reverse-derives battalion_no when possible)
      - company: 1..4 OR Q/R/S/T
      - platoon: 1..4 OR A/B/C/D
      - group: 1..4 OR E/F/G/H

    Outputs:
      - battalion_no
      - battalion_fal
      - battalion_second   (e.g. "Q" from "VQ")
      - company_letter     (Q/R/S/T)
      - platoon_letter     (A/B/C/D)
      - group_letter       (E/F/G/H)
      - company_callsign   (e.g. "SQ" for S within battalion VQ)
      - platoon_callsign   (e.g. "BS" = platoon B, company S)
      - group_callsign     (e.g. "BSFB" = platoon_callsign + group_letter + platoon_letter)
    """
    out: Dict[str, Any] = {}

    fal_map = _policy_fal_map(policy_cfg)
    fal_rev = {v: k for k, v in fal_map.items()}

    # ---- battalion_no
    bn_no = None

    # explicit numeric battalion_no/battalion
    if ctx.get("battalion_no") is not None:
        bn_no = _int(ctx.get("battalion_no"), 0) or None
    elif ctx.get("battalion") is not None:
        bn_no = _int(ctx.get("battalion"), 0) or None

    # unit like 46HV
    if bn_no is None:
        unit = _s(ctx.get("unit"))
        if unit:
            bn_no = battalion_no_from_unit(unit)

    # reverse from battalion_fal
    battalion_fal_in = _upper(ctx.get("battalion_fal"))
    if bn_no is None and len(battalion_fal_in) >= 2:
        bn_no = fal_rev.get(battalion_fal_in[:2])

    if bn_no:
        out["battalion_no"] = bn_no

    # ---- battalion_fal
    battalion_fal = battalion_fal_in[:2] if len(battalion_fal_in) >= 2 else ""
    if not battalion_fal and bn_no and bn_no in fal_map:
        battalion_fal = fal_map[bn_no]

    if battalion_fal:
        out["battalion_fal"] = battalion_fal
        out["battalion_second"] = battalion_fal[1:2]

    # ---- letters
    comp_let = company_letter(ctx.get("company"))
    plat_let = platoon_letter(ctx.get("platoon"))
    grp_let = group_letter(ctx.get("group"))

    if comp_let:
        out["company_letter"] = comp_let
    if plat_let:
        out["platoon_letter"] = plat_let
    if grp_let:
        out["group_letter"] = grp_let

    # ---- callsign building blocks
    # Company callsign: company letter + battalion second letter (RQ/SQ/TQ for VQ)
    batt_second = out.get("battalion_second") or ""
    if comp_let and batt_second:
        out["company_callsign"] = f"{comp_let}{batt_second}"

    # Platoon callsign: platoon letter + company letter (BS = platoon B, company S)
    if plat_let and comp_let:
        out["platoon_callsign"] = f"{plat_let}{comp_let}"

    # Group callsign: platoon_callsign + group letter + platoon letter (BSFB)
    pl_cs = out.get("platoon_callsign") or ""
    if pl_cs and grp_let and plat_let:
        out["group_callsign"] = f"{pl_cs}{grp_let}{plat_let}"

    return out
