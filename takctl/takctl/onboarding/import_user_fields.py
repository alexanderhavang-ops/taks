from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

FIELD_ALIASES: Dict[str, List[str]] = {
    "username": [
        "username", "user", "name", "login", "account", "userid", "user_id",
        "anvandarnamn", "användarnamn",
    ],
    "email": [
        "email", "e_mail", "e-mail", "mail", "epost", "e_post", "e-post",
        "attendee_email", "attendee_e_mail",
    ],
    "first_name": [
        "first_name", "firstname", "first", "given_name", "givenname",
        "fornamn", "förnamn", "attendee_first_name",
    ],
    "last_name": [
        "last_name", "lastname", "last", "surname", "family_name", "familyname",
        "efternamn", "attendee_last_name",
    ],
    "callsign": [
        "callsign", "call_sign", "call-sign", "anropssignal",
    ],
    "password": [
        "password", "pass", "pw", "losenord", "lösenord",
    ],
    "is_admin": [
        "is_admin", "admin", "administrator", "taks_admin", "marti_admin",
    ],
    "groups": [
        "groups", "group", "grupper", "grupp",
    ],
    "group1": [
        "group1", "group_1", "group_a", "group_primary", "grp1",
    ],
    "group2": [
        "group2", "group_2", "group_b", "group_secondary", "grp2",
    ],
    "group3": [
        "group3", "group_3", "group_c", "group_tertiary", "grp3",
    ],
    "policy_id": ["policy_id", "policy", "policyid"],
    "battalion": ["battalion", "bataljon"],
    "battalion_fal": ["battalion_fal", "bataljon_fal"],
    "company": ["company", "kompani"],
    "platoon": ["platoon", "pluton"],
    "n": ["n", "number", "nummer"],
    "team": ["team", "lag"],
    "atak_role_type": ["atak_role_type", "atak_role", "role", "roll"],
    "remarks": ["remarks", "comment", "comments", "kommentar", "kommentarer"],
}

IDENTITY_FIELDS = ["company", "platoon", "group", "n"]


def norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    out: List[str] = []
    for ch in text:
        if ch.isalnum() or ch in ("_", "-", " "):
            out.append(ch)
    return "".join(out).replace(" ", "_").replace("-", "_")


def field_for_header(header: Any) -> str | None:
    h = norm_header(header)
    if not h:
        return None

    for field, aliases in FIELD_ALIASES.items():
        if h == field or h in {norm_header(x) for x in aliases}:
            return field

    return None


def map_headers(headers: List[str]) -> Tuple[Dict[int, str], List[str], List[str]]:
    normed = [norm_header(h) for h in headers]
    mapping: Dict[int, str] = {}
    unmapped: List[str] = []
    used_singletons = set()

    # Repeated group1/group2/group3 are not useful, but other repeated fields are
    # also ignored to keep imports deterministic.
    for i, raw in enumerate(headers):
        field = field_for_header(raw)
        if field and field not in used_singletons:
            mapping[i] = field
            used_singletons.add(field)
        else:
            unmapped.append(raw)

    return mapping, unmapped, normed


def derive_username_from_email(email: Any) -> str:
    text = str(email or "").strip().lower()
    if "@" not in text:
        return ""

    local = text.split("@", 1)[0].strip()
    local = re.sub(r"[^a-z0-9._-]+", ".", local)
    local = re.sub(r"[.]{2,}", ".", local).strip("._-")
    return local


def derive_username(row: Dict[str, str]) -> str:
    username = str((row or {}).get("username") or "").strip()
    if username:
        return username
    return derive_username_from_email((row or {}).get("email"))


def canonicalize_row(row: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}

    for raw_k, raw_v in (row or {}).items():
        field = field_for_header(raw_k)
        if not field:
            continue
        v = "" if raw_v is None else str(raw_v).strip()

        if field == "groups":
            out[field] = v
        elif field not in out or not out.get(field):
            out[field] = v

    username = derive_username(out)
    if username:
        out["username"] = username

    return out


def help_rows() -> List[Tuple[str, str]]:
    return [
        ("username", "username, user, login"),
        ("email", "email, e-mail, mail, attendee email"),
        ("first_name", "first name, firstname, attendee first name"),
        ("last_name", "last name, lastname, attendee last name"),
        ("callsign", "callsign, call sign, anropssignal"),
        ("groups", "groups, group, grupp"),
        ("group1/group2/group3", "group1, group2, group3"),
        ("password", "password, pass, pw"),
        ("is_admin", "is_admin, admin, administrator"),
        ("company/platoon/group/n", "company, platoon, group, n"),
        ("team", "team"),
        ("atak_role_type", "atak_role_type, role"),
        ("remarks", "remarks, comments"),
    ]
