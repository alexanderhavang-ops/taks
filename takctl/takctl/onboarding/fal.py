from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


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
# Company: allow "P" (virtual/0) + Q/R/S/T (1..4)
_COMPANY_NUM_TO_LET = {0: "P", 1: "Q", 2: "R", 3: "S", 4: "T"}
_COMPANY_LET_TO_NUM = {v: k for k, v in _COMPANY_NUM_TO_LET.items()}

# Platoon: A..D (1..4)
_PLATOON_NUM_TO_LET = {1: "A", 2: "B", 3: "C", 4: "D"}
_PLATOON_LET_TO_NUM = {v: k for k, v in _PLATOON_NUM_TO_LET.items()}

# Group: E..H (1..4)
_GROUP_NUM_TO_LET = {1: "E", 2: "F", 3: "G", 4: "H"}
_GROUP_LET_TO_NUM = {v: k for k, v in _GROUP_NUM_TO_LET.items()}

_EXPECT_COMPANY = set(_COMPANY_LET_TO_NUM.keys())  # P/Q/R/S/T
_EXPECT_PLATOON = set(_PLATOON_LET_TO_NUM.keys())  # A/B/C/D
_EXPECT_GROUP = set(_GROUP_LET_TO_NUM.keys())      # E/F/G/H


def _letter_and_num(
    raw: Any,
    let_to_num: Dict[str, int],
    num_to_let: Dict[int, str],
    expected_letters: set[str],
    kind: str,
) -> Tuple[str, Optional[int], Optional[str]]:
    """
    KISS:
      - If user typed a single letter A-Z => accept it as-is.
        If not in expected_letters => emit warning (but do not fail).
        If it exists in let_to_num => also derive the numeric.
      - Else if user typed a number => derive letter via num_to_let (if known) + numeric.
      - Else empty => empty.
    """
    s = _upper(raw)
    if not s:
        return "", None, None

    # Letter input
    if len(s) == 1 and ("A" <= s <= "Z"):
        num = let_to_num.get(s)
        warn = None
        if s not in expected_letters:
            warn = f"{kind}_letter '{s}' is unusual (expected {''.join(sorted(expected_letters))})"
        return s, num, warn

    # Numeric input (including "0", "1", "2" ...)
    n = _int(raw, 0)
    if n == 0 and str(_s(raw)).strip() not in ("0", "0.0"):
        # non-numeric junk -> treat as empty but warn gently
        return "", None, f"{kind} value '{_s(raw)}' is not a valid letter or number"
    let = num_to_let.get(n, "")
    # If number is outside mapping, keep numeric but warn
    warn = None
    if not let:
        warn = f"{kind}_num '{n}' is unusual (no mapping to letter)"
    return let, n, warn


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
      - company: number OR letter (P/Q/R/S/T or any A-Z -> warning if unusual)
      - platoon: number OR letter (A/B/C/D or any A-Z -> warning if unusual)
      - group: number OR letter (E/F/G/H or any A-Z -> warning if unusual)

    Outputs (best-effort, never throws):
      - battalion_no
      - battalion_fal
      - battalion_second   (e.g. "Q" from "VQ")
      - company_letter / platoon_letter / group_letter
      - company_num / platoon_num / group_num (when derivable)
      - company_callsign / platoon_callsign / group_callsign
      - warnings: [ ... ]  (optional)
    """
    ctx = dict(ctx or {})
    out: Dict[str, Any] = {}
    warnings: list[str] = []

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

    # reverse from battalion_fal (only works if policy map provides reverse uniqueness)
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

    # ---- company/platoon/group letters + nums (accept-any-letter, warn-if-unusual)
    comp_let, comp_num, w = _letter_and_num(ctx.get("company"), _COMPANY_LET_TO_NUM, _COMPANY_NUM_TO_LET, _EXPECT_COMPANY, "company")
    if w: warnings.append(w)
    plat_let, plat_num, w = _letter_and_num(ctx.get("platoon"), _PLATOON_LET_TO_NUM, _PLATOON_NUM_TO_LET, _EXPECT_PLATOON, "platoon")
    if w: warnings.append(w)
    grp_let, grp_num, w = _letter_and_num(ctx.get("group"), _GROUP_LET_TO_NUM, _GROUP_NUM_TO_LET, _EXPECT_GROUP, "group")
    if w: warnings.append(w)

    if comp_let: out["company_letter"] = comp_let
    if plat_let: out["platoon_letter"] = plat_let
    if grp_let: out["group_letter"] = grp_let

    if comp_num is not None: out["company_num"] = comp_num
    if plat_num is not None: out["platoon_num"] = plat_num
    if grp_num is not None: out["group_num"] = grp_num

    # ---- callsign building blocks (best-effort; only build when pieces exist)
    batt_second = out.get("battalion_second") or ""

    # Company callsign: company letter + battalion second letter (RQ/SQ/TQ for VQ)
    if comp_let and batt_second:
        out["company_callsign"] = f"{comp_let}{batt_second}"

    # Platoon callsign: platoon letter + company letter (BS = platoon B, company S)
    if plat_let and comp_let:
        out["platoon_callsign"] = f"{plat_let}{comp_let}"

    # Group callsign: platoon_callsign + group letter + platoon letter (BSFB)
    pl_cs = out.get("platoon_callsign") or ""
    if pl_cs and grp_let and plat_let:
        out["group_callsign"] = f"{pl_cs}{grp_let}{plat_let}"

    if warnings:
        out["warnings"] = warnings

    return out
