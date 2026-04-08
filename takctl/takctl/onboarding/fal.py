from __future__ import annotations

import re
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
    Best-effort:
      - "46HV" -> 46
      - "48HVBAT" -> 48
      - "48hvbat" -> 48
    """
    u = _upper(unit)
    m = re.match(r"^(\d+)(HVBAT|HV)$", u)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


# -----------------------------
# Hemvärn / FAL-A letter helpers
# -----------------------------
# Company: allow P (0/stab), Q/R/S/T (1..4), plus known reserve/other slots.
_COMPANY_NUM_TO_LET = {
    0: "P",
    1: "Q",
    2: "R",
    3: "S",
    4: "T",
    5: "X",
    6: "N",
    7: "U",
    8: "W",
}
_COMPANY_LET_TO_NUM = {v: k for k, v in _COMPANY_NUM_TO_LET.items()}

# Platoon: A..G (1..7)
_PLATOON_NUM_TO_LET = {
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "E",
    6: "F",
    7: "G",
}
_PLATOON_LET_TO_NUM = {v: k for k, v in _PLATOON_NUM_TO_LET.items()}

# Group: E..M (1..9)
_GROUP_NUM_TO_LET = {
    1: "E",
    2: "F",
    3: "G",
    4: "H",
    5: "I",
    6: "J",
    7: "K",
    8: "L",
    9: "M",
}
_GROUP_LET_TO_NUM = {v: k for k, v in _GROUP_NUM_TO_LET.items()}

_EXPECT_COMPANY = set(_COMPANY_LET_TO_NUM.keys())   # P/Q/R/S/T/X/N/U/W
_EXPECT_PLATOON = set(_PLATOON_LET_TO_NUM.keys())   # A..G
_EXPECT_GROUP = set(_GROUP_LET_TO_NUM.keys())       # E..M


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
        return "", None, f"{kind} value '{_s(raw)}' is not a valid letter or number"

    let = num_to_let.get(n, "")
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
    Add derived keys to ctx (non-destructive). This is context enrichment.

    Inputs supported:
      - battalion_no (e.g. 46) OR battalion (e.g. "46") OR unit ("46HV")
      - battalion_fal (e.g. "VQ")  (reverse-derives battalion_no when possible)
      - company: number OR letter
      - platoon: number OR letter
      - group: number OR letter

    Outputs (best-effort, never throws):
      - battalion_no
      - battalion_fal
      - battalion_second   (e.g. "Q" from "VQ")
      - company_letter / platoon_letter / group_letter
      - company_num / platoon_num / group_num
      - company_callsign   (e.g. RQ)
      - company_fal        (alias of company_callsign)
      - platoon_fal        (e.g. AR)
      - group_fal          (e.g. EA)
      - warnings: [ ... ]

    IMPORTANT:
      - We do NOT emit any ambiguous "group_callsign".
      - FAL-TAK is a special-case assembly and should be built in identity_grammar.py.
    """
    ctx = dict(ctx or {})
    out: Dict[str, Any] = {}
    warnings: list[str] = []

    fal_map = _policy_fal_map(policy_cfg)
    fal_rev = {v: k for k, v in fal_map.items()}

    # ---- battalion_no
    bn_no = None

    if ctx.get("battalion_no") is not None:
        bn_no = _int(ctx.get("battalion_no"), 0) or None
    elif ctx.get("battalion") is not None:
        bn_no = _int(ctx.get("battalion"), 0) or None

    if bn_no is None:
        unit = _s(ctx.get("unit"))
        if unit:
            bn_no = battalion_no_from_unit(unit)

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

    # ---- company/platoon/group letters + nums
    comp_let, comp_num, w = _letter_and_num(
        ctx.get("company"),
        _COMPANY_LET_TO_NUM,
        _COMPANY_NUM_TO_LET,
        _EXPECT_COMPANY,
        "company",
    )
    if w:
        warnings.append(w)

    plat_let, plat_num, w = _letter_and_num(
        ctx.get("platoon"),
        _PLATOON_LET_TO_NUM,
        _PLATOON_NUM_TO_LET,
        _EXPECT_PLATOON,
        "platoon",
    )
    if w:
        warnings.append(w)

    grp_let, grp_num, w = _letter_and_num(
        ctx.get("group"),
        _GROUP_LET_TO_NUM,
        _GROUP_NUM_TO_LET,
        _EXPECT_GROUP,
        "group",
    )
    if w:
        warnings.append(w)

    if comp_let:
        out["company_letter"] = comp_let
    if plat_let:
        out["platoon_letter"] = plat_let
    if grp_let:
        out["group_letter"] = grp_let

    if comp_num is not None:
        out["company_num"] = comp_num
    if plat_num is not None:
        out["platoon_num"] = plat_num
    if grp_num is not None:
        out["group_num"] = grp_num

    # ---- doctrinal building blocks
    batt_second = out.get("battalion_second") or ""

    # Company FAL: company letter + battalion second letter (e.g. RQ for battalion VQ)
    company_callsign = ""
    if comp_let and batt_second:
        company_callsign = f"{comp_let}{batt_second}"
        out["company_callsign"] = company_callsign
        out["company_fal"] = company_callsign

    # Platoon FAL: platoon letter + company letter (AR/BS/etc)
    platoon_fal = ""
    if plat_let and comp_let:
        platoon_fal = f"{plat_let}{comp_let}"
        out["platoon_fal"] = platoon_fal

    # Group FAL: group letter + platoon letter (EA/FB/etc)
    group_fal = ""
    if grp_let and plat_let:
        group_fal = f"{grp_let}{plat_let}"
        out["group_fal"] = group_fal

    if warnings:
        out["warnings"] = warnings

    return out


# -----------------------------------------------------------------------------
# Reverse parsing
# -----------------------------------------------------------------------------

_CALLSIGN_RE = re.compile(r"^([A-Z]+?)(\d+)?$")


def _kind_scope_rank(kind: str) -> int:
    """
    Narrower / lower-level units get higher rank.

      battalion_or_other_fal : 0
      company_fal            : 1
      platoon_fal            : 2
      group_fal              : 3
    """
    return {
        "battalion_or_other_fal": 0,
        "company_fal": 1,
        "platoon_fal": 2,
        "group_fal": 3,
    }.get(kind, -1)


def _parse_fal_pair(pair: str) -> Optional[Dict[str, Any]]:
    """
    Parse a doctrinal 2-letter FAL pair.

    Returns one of:
      - battalion_or_other_fal (fallback generic 2-letter FAL)
      - company_fal            : <company><battalion-second>
      - platoon_fal            : <platoon><company>
      - group_fal              : <group><platoon>
    """
    p = _upper(pair)
    if len(p) != 2:
        return None

    a, b = p[0], p[1]

    # Most specific first
    if a in _EXPECT_GROUP and b in _EXPECT_PLATOON:
        return {
            "kind": "group_fal",
            "pair": p,
            "group_letter": a,
            "platoon_letter": b,
            "group_num": _GROUP_LET_TO_NUM.get(a),
            "platoon_num": _PLATOON_LET_TO_NUM.get(b),
        }

    if a in _EXPECT_PLATOON and b in _EXPECT_COMPANY:
        return {
            "kind": "platoon_fal",
            "pair": p,
            "platoon_letter": a,
            "company_letter": b,
            "platoon_num": _PLATOON_LET_TO_NUM.get(a),
            "company_num": _COMPANY_LET_TO_NUM.get(b),
        }

    if a in _EXPECT_COMPANY:
        return {
            "kind": "company_fal",
            "pair": p,
            "company_letter": a,
            "battalion_second": b,
            "company_num": _COMPANY_LET_TO_NUM.get(a),
        }

    # Fallback: still a valid-looking 2-letter FAL, but level unknown/generic.
    return {
        "kind": "battalion_or_other_fal",
        "pair": p,
        "battalion_fal": p,
        "battalion_second": b,
    }


def _maybe_resolve_battalion_no(policy_cfg, battalion_fal: str) -> Optional[int]:
    if not battalion_fal:
        return None
    fal_map = _policy_fal_map(policy_cfg)
    rev = {v: k for k, v in fal_map.items()}
    return rev.get(_upper(battalion_fal))


def _derive_role_metadata(out: Dict[str, Any]) -> Dict[str, Any]:
    """
    Derived semantics on top of parsed structure.

    IMPORTANT:
      - No trailing number => this callsign refers to a UNIT.
      - Trailing number    => this callsign refers to an INDIVIDUAL within that unit.
      - We only emit role *hints* from numeric convention:
          1 -> leader
          2 -> deputy
          3+ -> member
      - These are intentionally hints, not doctrinal truth.
    """
    individual = out.get("individual")
    grammar = out.get("grammar")
    is_individual = individual is not None
    is_unit = not is_individual

    out["is_unit"] = is_unit
    out["is_individual"] = is_individual
    out["entity_kind"] = "unit" if is_unit else "individual"

    role_level = "unknown"
    if grammar == "FAL_TAK":
        role_level = "group"
    elif grammar == "FAL":
        k = out.get("kind")
        if k == "group_fal":
            role_level = "group"
        elif k == "platoon_fal":
            role_level = "platoon"
        elif k == "company_fal":
            role_level = "company"
        elif k == "battalion_or_other_fal":
            role_level = "battalion_or_other"
    elif grammar == "FALFAL":
        bk = str(out.get("base_kind") or "")
        if bk == "group_fal":
            role_level = "group"
        elif bk == "platoon_fal":
            role_level = "platoon"
        elif bk == "company_fal":
            role_level = "company"
        elif bk == "battalion_or_other_fal":
            role_level = "battalion_or_other"

    out["role_level"] = role_level

    if is_unit:
        out["role_hint"] = "unit"
        out["role_source"] = "no_individual_suffix"
        out["role_confidence"] = "high"
        return out

    if individual == 1:
        out["role_hint"] = "leader"
        out["role_source"] = "individual_suffix_convention"
        out["role_confidence"] = "medium"
    elif individual == 2:
        out["role_hint"] = "deputy"
        out["role_source"] = "individual_suffix_convention"
        out["role_confidence"] = "medium"
    elif individual >= 3:
        out["role_hint"] = "member"
        out["role_source"] = "individual_suffix_convention"
        out["role_confidence"] = "medium"
    else:
        out["role_hint"] = "unknown"
        out["role_source"] = "individual_suffix_convention"
        out["role_confidence"] = "low"

    return out


def parse_callsign(policy_cfg, callsign: str) -> Dict[str, Any]:
    """
    Reverse parser for:
      - FAL       : <FAL><n?>
      - FALFAL    : <lowest_unit_fal><identifier_fal><n?>
      - FAL-TAK   : <Platoon><Company><Group><Platoon><n?>

    Examples:
      - EA3    -> FAL
      - EAXW1  -> FALFAL
      - AQEA1  -> FAL_TAK

    Notes:
      - FAL-TAK is recognized by repeated platoon letter:
          pos1 == pos4
          pos1 in platoon letters
          pos2 in company letters
          pos3 in group letters
      - FALFAL requires TWO valid FAL pairs in doctrinal order:
          lowest / narrowest unit first, broader identifier second.
        So EAXW is valid, but XWEA is rejected.
      - If only one 2-letter FAL pair is present, grammar=FAL.

    IMPORTANT FOR LLM / presence consumers:
      - No numeric suffix means the callsign refers to a UNIT.
        Example: VW, TQ, EA
      - Numeric suffix means the callsign refers to an INDIVIDUAL within that unit.
        Example: VW1, TQ2, EA3
      - Units can absolutely emit CoT themselves (e.g. staff laptop, company node, HQ node).
    """
    raw = _upper(callsign)
    if not raw:
        raise RuntimeError("empty callsign")

    m = _CALLSIGN_RE.match(raw)
    if not m:
        raise RuntimeError(f"invalid callsign format: {callsign}")

    letters = _upper(m.group(1))
    n_raw = m.group(2) or ""
    individual = int(n_raw) if n_raw else None

    out: Dict[str, Any] = {
        "callsign": raw,
        "letters": letters,
        "individual": individual,
        "grammar": None,
    }

    # ---- FAL-TAK: PlatoonCompanyGroupPlatoon
    if len(letters) == 4:
        p1, c1, g1, p2 = letters[0], letters[1], letters[2], letters[3]
        if p1 == p2 and p1 in _EXPECT_PLATOON and c1 in _EXPECT_COMPANY and g1 in _EXPECT_GROUP:
            out.update({
                "grammar": "FAL_TAK",
                "platoon_letter": p1,
                "company_letter": c1,
                "group_letter": g1,
                "platoon_num": _PLATOON_LET_TO_NUM.get(p1),
                "company_num": _COMPANY_LET_TO_NUM.get(c1),
                "group_num": _GROUP_LET_TO_NUM.get(g1),
                "platoon_fal": f"{p1}{c1}",
                "group_fal": f"{g1}{p1}",
            })
            return _derive_role_metadata(out)

    # ---- FAL: exactly one FAL pair
    if len(letters) == 2:
        p = _parse_fal_pair(letters)
        if p is None:
            raise RuntimeError(f"unable to parse FAL pair: {letters}")

        out["grammar"] = "FAL"
        out.update(p)

        kind = str(p.get("kind") or "")
        if kind == "group_fal":
            out["group_fal"] = letters
        elif kind == "platoon_fal":
            out["platoon_fal"] = letters
        elif kind == "company_fal":
            out["company_fal"] = letters
        elif kind == "battalion_or_other_fal":
            out["battalion_fal"] = letters
            bn = _maybe_resolve_battalion_no(policy_cfg, str(p.get("battalion_fal") or ""))
            if bn is not None:
                out["battalion_no"] = bn

        return _derive_role_metadata(out)

    # ---- FALFAL: two consecutive FAL pairs in doctrinal order
    if len(letters) == 4:
        lower_pair = letters[:2]
        ident_pair = letters[2:]
        lower = _parse_fal_pair(lower_pair)
        ident = _parse_fal_pair(ident_pair)

        if lower is not None and ident is not None:
            lower_kind = str(lower.get("kind") or "")
            ident_kind = str(ident.get("kind") or "")
            lower_rank = _kind_scope_rank(lower_kind)
            ident_rank = _kind_scope_rank(ident_kind)

            # Doctrinal FALFAL must be lowest/narrowest first, broader second.
            if lower_rank > ident_rank:
                out["grammar"] = "FALFAL"
                out["base_fal"] = lower_pair
                out["identifier_fal"] = ident_pair
                out["base"] = lower
                out["identifier"] = ident
                out["base_kind"] = lower_kind
                out["identifier_kind"] = ident_kind

                # Flatten the useful organizational fields from the lowest unit first.
                if lower_kind == "group_fal":
                    out["group_fal"] = lower_pair
                    out["group_letter"] = lower.get("group_letter")
                    out["group_num"] = lower.get("group_num")
                    out["platoon_letter"] = lower.get("platoon_letter")
                    out["platoon_num"] = lower.get("platoon_num")
                elif lower_kind == "platoon_fal":
                    out["platoon_fal"] = lower_pair
                    out["platoon_letter"] = lower.get("platoon_letter")
                    out["platoon_num"] = lower.get("platoon_num")
                    out["company_letter"] = lower.get("company_letter")
                    out["company_num"] = lower.get("company_num")
                elif lower_kind == "company_fal":
                    out["company_fal"] = lower_pair
                    out["company_letter"] = lower.get("company_letter")
                    out["company_num"] = lower.get("company_num")
                    out["battalion_second"] = lower.get("battalion_second")
                elif lower_kind == "battalion_or_other_fal":
                    out["battalion_fal"] = lower_pair
                    out["battalion_second"] = lower.get("battalion_second")
                    bn = _maybe_resolve_battalion_no(policy_cfg, lower_pair)
                    if bn is not None:
                        out["battalion_no"] = bn

                # Flatten useful identifier information as broader scope context.
                if ident_kind == "company_fal":
                    out["identifier_company_fal"] = ident_pair
                    out.setdefault("company_letter", ident.get("company_letter"))
                    out.setdefault("company_num", ident.get("company_num"))
                    out.setdefault("battalion_second", ident.get("battalion_second"))
                elif ident_kind == "battalion_or_other_fal":
                    out["identifier_battalion_fal"] = ident_pair
                    out.setdefault("battalion_fal", ident_pair)
                    out.setdefault("battalion_second", ident.get("battalion_second"))
                    bn = _maybe_resolve_battalion_no(policy_cfg, ident_pair)
                    if bn is not None:
                        out["battalion_no"] = bn
                elif ident_kind == "platoon_fal":
                    out["identifier_platoon_fal"] = ident_pair
                elif ident_kind == "group_fal":
                    out["identifier_group_fal"] = ident_pair

                return _derive_role_metadata(out)

    raise RuntimeError(f"unable to classify callsign: {callsign}")
