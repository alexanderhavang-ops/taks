from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
import os
import xml.etree.ElementTree as ET


class UserAuthFileError(RuntimeError):
    pass


@dataclass(frozen=True)
class UserAuthRecord:
    username: str
    role: Optional[str]
    fingerprint: Optional[str]
    groups_rw: List[str]
    groups_in: List[str]
    groups_out: List[str]
    source_path: str


def _split_groups(s: Optional[str]) -> List[str]:
    if not s:
        return []
    parts: List[str] = []
    for chunk in s.replace(",", " ").split():
        c = chunk.strip()
        if c:
            parts.append(c)
    # preserve order, de-dupe
    seen = set()
    out: List[str] = []
    for g in parts:
        if g not in seen:
            out.append(g)
            seen.add(g)
    return out


def _tag_localname(tag: str) -> str:
    # "{namespace}Tag" -> "Tag"
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _get_attr_ci(elem: ET.Element, want: str) -> Optional[str]:
    """Case-insensitive attribute fetch (XML attrs are case-sensitive, but configs vary in the wild)."""
    w = want.lower()
    for k, v in elem.attrib.items():
        if k.lower() == w:
            s = (v or "").strip()
            return s if s else None
    return None


def _find_descendant_file_location_under_auth(root: ET.Element) -> Optional[str]:
    """
    Find <auth> ... <File location="..."/> specifically.
    We do NOT pick arbitrary <File> nodes elsewhere in CoreConfig.
    """
    for elem in root.iter():
        if _tag_localname(elem.tag).lower() != "auth":
            continue

        for sub in elem.iter():
            if _tag_localname(sub.tag).lower() != "file":
                continue

            # Most common: location="..."
            loc = _get_attr_ci(sub, "location")
            if loc:
                return loc

    return None


def debug_auth_resolution(coreconfig_path: str) -> Dict[str, Any]:
    """
    Debug helper so failures become self-explanatory.
    Returns what we could determine WITHOUT raising, unless CoreConfig is unreadable.
    """
    core = Path(coreconfig_path)
    dbg: Dict[str, Any] = {
        "coreconfig_path": str(core),
        "coreconfig_exists": core.exists(),
        "coreconfig_abs": str(core.resolve()) if core.exists() else str(core),
        "coreconfig_dir": str(core.parent.resolve()),
        "parse_ok": False,
        "found_auth": False,
        "found_file_under_auth": False,
        "file_location_raw": None,
        "resolved_auth_xml": None,
        "auth_xml_exists": None,
        "auth_xml_readable": None,
        "notes": [],
    }

    if not core.exists():
        dbg["notes"].append("CoreConfig not found")
        return dbg

    try:
        tree = ET.parse(str(core))
        root = tree.getroot()
        dbg["parse_ok"] = True
    except Exception as e:
        raise UserAuthFileError(f"Failed to parse CoreConfig.xml: {e}") from e

    # Determine if we even saw an <auth> element
    for elem in root.iter():
        if _tag_localname(elem.tag).lower() == "auth":
            dbg["found_auth"] = True
            break

    loc = _find_descendant_file_location_under_auth(root)
    if loc:
        dbg["found_file_under_auth"] = True
        dbg["file_location_raw"] = loc

        p = Path(loc)
        resolved = p if p.is_absolute() else (core.parent / p)
        dbg["resolved_auth_xml"] = str(resolved.resolve())
        dbg["auth_xml_exists"] = resolved.exists()
        dbg["auth_xml_readable"] = os.access(str(resolved), os.R_OK)

    return dbg


def _resolve_auth_file_path(coreconfig_path: str) -> Path:
    core = Path(coreconfig_path)
    if not core.exists():
        raise UserAuthFileError(f"CoreConfig not found: {core}")

    try:
        tree = ET.parse(str(core))
        root = tree.getroot()
    except Exception as e:
        raise UserAuthFileError(f"Failed to parse CoreConfig.xml: {e}") from e

    loc = _find_descendant_file_location_under_auth(root)
    if not loc:
        dbg = debug_auth_resolution(coreconfig_path)
        raise UserAuthFileError(
            "Could not find <auth>...<File location=...> in CoreConfig.xml. "
            f"debug={dbg}"
        )

    p = Path(loc)
    if p.is_absolute():
        return p

    # Relative to CoreConfig.xml directory (usually /opt/tak/)
    return core.parent / p


def _get_text_child(parent: ET.Element, child_name: str) -> Optional[str]:
    want = child_name.lower()
    for ch in list(parent):
        if _tag_localname(ch.tag).lower() == want:
            t = (ch.text or "").strip()
            return t if t else None
    return None


def _username_of_user_elem(u: ET.Element) -> Optional[str]:
    # TAK's UserAuthenticationFile.xml uses identifier="..."
    for k in ("identifier", "username", "name", "user", "uid"):
        v = u.attrib.get(k)
        if v and v.strip():
            return v.strip()

    # fallback child elements (rare in TAK, but keep)
    for suffix in ("identifier", "username", "name"):
        t = _get_text_child(u, suffix)
        if t:
            return t

    return None


def _looks_like_user_elem(u: ET.Element) -> bool:
    return _username_of_user_elem(u) is not None


def load_user_auth_records(coreconfig_path: str) -> Dict[str, UserAuthRecord]:
    """
    Load the authentication XML file and return records keyed by username.

    READ-ONLY by design.
    """
    auth_path = _resolve_auth_file_path(coreconfig_path)
    if not auth_path.exists():
        raise UserAuthFileError(f"User auth XML not found: {auth_path}")

    try:
        tree = ET.parse(str(auth_path))
        root = tree.getroot()
    except Exception as e:
        raise UserAuthFileError(f"Failed to parse auth XML {auth_path}: {e}") from e

    records: Dict[str, UserAuthRecord] = {}

    for elem in root.iter():
        if _tag_localname(elem.tag).lower() != "user":
            continue
        if not _looks_like_user_elem(elem):
            continue

        username = _username_of_user_elem(elem)
        if not username:
            continue

        role = elem.attrib.get("role") or _get_text_child(elem, "role")

        fingerprint = (
            elem.attrib.get("fingerprint")
            or elem.attrib.get("fingerPrint")
            or _get_text_child(elem, "fingerprint")
            or _get_text_child(elem, "fingerPrint")
        )

        groups_rw = _split_groups(elem.attrib.get("groupList") or _get_text_child(elem, "groupList"))
        groups_in = _split_groups(elem.attrib.get("groupListIN") or _get_text_child(elem, "groupListIN"))
        groups_out = _split_groups(elem.attrib.get("groupListOUT") or _get_text_child(elem, "groupListOUT"))

        records[username] = UserAuthRecord(
            username=username,
            role=role,
            fingerprint=fingerprint,
            groups_rw=groups_rw,
            groups_in=groups_in,
            groups_out=groups_out,
            source_path=str(auth_path),
        )

    return records


def get_user_auth_record(coreconfig_path: str, username: str) -> UserAuthRecord:
    records = load_user_auth_records(coreconfig_path)
    if username not in records:
        raise UserAuthFileError(f"User '{username}' not found in auth XML")
    return records[username]


def list_users(coreconfig_path: str) -> List[UserAuthRecord]:
    records = load_user_auth_records(coreconfig_path)
    return [records[k] for k in sorted(records.keys(), key=lambda s: s.lower())]


def auth_file_path(coreconfig_path: str) -> str:
    return str(_resolve_auth_file_path(coreconfig_path))

