from __future__ import annotations


def _n(x) -> str:
    return str(x or "").strip()


def build_nameplate(username: str, ident: dict | None, groups: list[str] | None = None) -> tuple[str, str]:
    ident = ident or {}
    groups = groups or []

    callsign = _n(ident.get("callsign")) or _n(username) or "—"

    bits: list[str] = []

    if _n(ident.get("battalion_fal")):
        bits.append(_n(ident.get("battalion_fal")))
    elif _n(ident.get("battalion")):
        bits.append(f"{_n(ident.get('battalion'))} HVBAT")

    if _n(ident.get("company")):
        bits.append(f"Kompani {_n(ident.get('company'))}")

    if _n(ident.get("platoon")):
        bits.append(f"Pluton {_n(ident.get('platoon'))}")

    if _n(ident.get("group")):
        bits.append(f"Grupp {_n(ident.get('group'))}")

    if _n(ident.get("n")):
        bits.append(f"EN {_n(ident.get('n'))}")

    row2 = " · ".join(bits)

    if not row2 and groups:
        row2 = " / ".join([_n(x) for x in groups if _n(x)])

    if not row2:
        row2 = callsign

    return callsign, row2
