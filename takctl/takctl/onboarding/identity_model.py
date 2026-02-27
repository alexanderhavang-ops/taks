from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class UserIdentity:
    username: str

    # --- Structural (TAKS semantics) ---
    battalion: Optional[str] = None
    company: Optional[str] = None
    platoon: Optional[str] = None
    squad: Optional[str] = None

    # --- Role ---
    role: Optional[str] = None
    battalion_role: Optional[str] = None
    atak_role_type: Optional[str] = None

    # --- Tactical (ATAK impacting) ---
    callsign: Optional[str] = None
    team: Optional[str] = None
    team_color: Optional[str] = None

    # --- Marti authority ---
    groups: List[str] = field(default_factory=list)

    # --- Metadata ---
    policy_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "identity": {
                "battalion": self.battalion,
                "company": self.company,
                "platoon": self.platoon,
                "squad": self.squad,
                "role": self.role,
                "battalion_role": self.battalion_role,
                "atak_role_type": self.atak_role_type,
                "callsign": self.callsign,
                "team": self.team,
                "team_color": self.team_color,
            },
            "marti": {
                "groups": list(self.groups),
            },
            "policy_id": self.policy_id,
        }
