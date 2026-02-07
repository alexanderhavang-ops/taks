from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence
import xml.etree.ElementTree as ET

from .models import UserRecord
from .user_directory import UserDirectory


def _strip_ns(tag: str) -> str:
    # "{namespace}Tag" -> "Tag"
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class UserDirectoryXml(UserDirectory):
    """
    Read-only UserDirectory backed by TAK Server's UserAuthenticationFile.xml

    Authoritative identity is external; takctl observes only.
    """

    def __init__(self, xml_path: str | Path = "/opt/tak/UserAuthenticationFile.xml"):
        self.xml_path = Path(xml_path)

    def list_users(self) -> Sequence[UserRecord]:
        root = self._load_root()

        users: list[UserRecord] = []
        for u in root:
            if _strip_ns(u.tag) != "User":
                continue
            username = u.attrib.get("identifier")
            if not username:
                continue

            groups = self._groups_from_user_elem(u)
            users.append(UserRecord(username=username, groups=groups))

        # stable ordering for UI/CLI
        users.sort(key=lambda x: x.username.lower())
        return users

    def get_user(self, username: str) -> Optional[UserRecord]:
        username = username.strip()
        if not username:
            return None

        for u in self.list_users():
            if u.username == username:
                return u
        return None

    def _load_root(self) -> ET.Element:
        if not self.xml_path.exists():
            raise FileNotFoundError(f"User auth XML not found: {self.xml_path}")
        tree = ET.parse(self.xml_path)
        return tree.getroot()

    def _groups_from_user_elem(self, user_elem: ET.Element) -> list[str]:
        groups: list[str] = []
        # groupList can appear multiple times, content can be whitespace/newlines
        for child in list(user_elem):
            if _strip_ns(child.tag) != "groupList":
                continue
            if child.text:
                # Some files have a single group per element; some may have whitespace.
                # We treat whitespace-separated tokens as groups, and keep "__ANON__" etc.
                for g in child.text.split():
                    if g and g not in groups:
                        groups.append(g)
        return groups

