from __future__ import annotations

import re
from typing import Any, Dict, List

from replay.org import infer_company_from_callsign


_UPK_RE = re.compile(r"^UPK\s+([1-3]\d\d)$")


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def parse_upk_label(label: Any) -> int:
    s = _s(label).upper()
    m = _UPK_RE.match(s)
    if not m:
        raise ValueError(f"invalid UPK label: {label!r}")
    return int(m.group(1))


def upk_echelon_from_number(number: int) -> str:
    if 100 <= int(number) <= 199:
        return "mr"
    if 200 <= int(number) <= 299:
        return "battalion"
    if 300 <= int(number) <= 399:
        return "company"
    raise ValueError(f"UPK number out of supported range: {number!r}")


def upk_echelon_from_label(label: Any) -> str:
    return upk_echelon_from_number(parse_upk_label(label))


def format_upk_label(number: int) -> str:
    n = int(number)
    echelon = upk_echelon_from_number(n)  # validates range
    _ = echelon
    return f"UPK {n}"


def empty_upk_registry() -> Dict[str, Any]:
    return {
        "mr": [],
        "battalion": [],
        "companies": {}
    }


def make_upk_entry(
    *,
    label: str,
    mgrs: str = "",
    lat: float | None = None,
    lon: float | None = None,
    owner_unit: str = "",
    purpose: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    number = parse_upk_label(label)
    echelon = upk_echelon_from_number(number)

    out: Dict[str, Any] = {
        "label": format_upk_label(number),
        "number": number,
        "echelon": echelon,
        "mgrs": _s(mgrs),
        "owner_unit": _s(owner_unit),
        "purpose": _s(purpose),
        "notes": _s(notes),
    }

    if lat is not None and lon is not None:
        out["lat"] = float(lat)
        out["lon"] = float(lon)

    return out


def add_upk_entry(registry: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    echelon = _s(entry.get("echelon")).lower()
    owner_unit = _s(entry.get("owner_unit")).upper()

    if echelon == "mr":
        registry.setdefault("mr", []).append(entry)
        return registry

    if echelon == "battalion":
        registry.setdefault("battalion", []).append(entry)
        return registry

    if echelon == "company":
        if not owner_unit:
            raise ValueError("company UPK requires owner_unit")
        companies = registry.setdefault("companies", {})
        companies.setdefault(owner_unit, []).append(entry)
        return registry

    raise ValueError(f"unsupported UPK echelon: {echelon!r}")


def list_upks_for_unit(registry: Dict[str, Any], unit_callsign: str) -> List[Dict[str, Any]]:
    unit = _s(unit_callsign).upper()
    out: List[Dict[str, Any]] = []

    out.extend(list(registry.get("mr") or []))
    out.extend(list(registry.get("battalion") or []))

    companies = registry.get("companies") or {}
    out.extend(list(companies.get(unit) or []))

    return out


def list_upks_for_recipient(
    registry: Dict[str, Any],
    *,
    recipient_unit: str,
    battalion_fal: str = "",
    company_unit: str = "",
) -> List[Dict[str, Any]]:
    recipient = _s(recipient_unit).upper()
    company = _s(company_unit).upper()

    if not company and battalion_fal:
        company = infer_company_from_callsign(recipient, battalion_fal)

    out: List[Dict[str, Any]] = []
    out.extend(list(registry.get("mr") or []))
    out.extend(list(registry.get("battalion") or []))

    companies = registry.get("companies") or {}

    if company:
        out.extend(list(companies.get(company) or []))
    else:
        out.extend(list(companies.get(recipient) or []))

    return out
