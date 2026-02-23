from __future__ import annotations

import os
import re
import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class Identity:
    callsign: str
    team: str
    atak_role_type: Optional[str] = None


class PolicyError(RuntimeError):
    pass


class Policy:
    """
    Loads a policy pack from:
      1) TAKS_POLICY_DIR (if set)
      2) /opt/tak/policies/<id>/policy.conf   (runtime)
      3) /opt/taks/policies/<id>/policy.conf  (source/dev)

    Policy id default:
      env TAKS_POLICY_ID or 'hemvarnet'
    """

    def __init__(self, policy_id: Optional[str] = None) -> None:
        self.policy_id = policy_id or os.environ.get("TAKS_POLICY_ID", "hemvarnet")
        self.path = self._resolve_path(self.policy_id)
        self.cfg = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(';', '#'))
        self.cfg.read(self.path, encoding="utf-8")

    @staticmethod
    def _resolve_path(policy_id: str) -> str:
        base = os.environ.get("TAKS_POLICY_DIR", "").strip()
        candidates = []
        if base:
            candidates.append(Path(base) / policy_id / "policy.conf")
            candidates.append(Path(base) / f"{policy_id}.conf")
            candidates.append(Path(base) / "policy.conf")

        candidates.extend([
            Path("/opt/tak/policies") / policy_id / "policy.conf",
            Path("/opt/taks/policies") / policy_id / "policy.conf",
        ])

        for p in candidates:
            try:
                if p.is_file():
                    return str(p)
            except Exception:
                continue

        raise PolicyError(
            f"policy.conf not found for policy_id={policy_id!r}. Tried: "
            + ", ".join(str(x) for x in candidates)
        )

    def meta(self) -> Dict[str, str]:
        if "meta" not in self.cfg:
            return {"id": self.policy_id}
        d = dict(self.cfg["meta"])
        d.setdefault("id", self.policy_id)
        return d

    # -------------------------
    # Normalization helpers
    # -------------------------
    def _normalize_callsign(self, s: str) -> str:
        sec = self.cfg["callsign"] if "callsign" in self.cfg else {}
        if sec.get("strip_spaces", "false").lower() in ("1", "true", "yes", "on"):
            s = s.replace(" ", "")
        if sec.get("normalize_upper", "false").lower() in ("1", "true", "yes", "on"):
            s = s.upper()
        # conservative: keep A-Z0-9_- only
        s = re.sub(r"[^A-Z0-9_\-]", "", s)
        return s

    # -------------------------
    # Team resolution
    # -------------------------
    def resolve_team(self, ctx: Dict[str, Any]) -> str:
        """
        ctx keys (optional):
          battalion_role: "staff"|"command"
          company: int/str
          platoon: int/str

        priority:
          battalion role -> company -> platoon -> defaults.team
        """
        batt_role = (ctx.get("battalion_role") or "").strip().lower()
        if batt_role and "team.battalion" in self.cfg:
            sec = self.cfg["team.battalion"]
            if batt_role in sec:
                return sec[batt_role].strip()

        company = ctx.get("company")
        if company is not None and "team.company" in self.cfg:
            sec = self.cfg["team.company"]
            k = str(company).strip()
            if k in sec:
                return sec[k].strip()

        platoon = ctx.get("platoon")
        if platoon is not None and "team.platoon" in self.cfg:
            sec = self.cfg["team.platoon"]
            k = str(platoon).strip()
            if k in sec:
                return sec[k].strip()

        if "team.defaults" in self.cfg and "team" in self.cfg["team.defaults"]:
            return self.cfg["team.defaults"]["team"].strip()

        return "Blue"

    # -------------------------
    # Callsign resolution
    # -------------------------
    def resolve_callsign(self, ctx: Dict[str, Any]) -> str:
        """
        ctx keys (optional):
          unit: str   (e.g. "BSFB")
          n: int/str  (e.g. 1,2,3)
          role: str   ("leader"|"member"|"staff"|...)
        """
        sec = self.cfg["callsign"] if "callsign" in self.cfg else {}
        unit = (ctx.get("unit") or "").strip()
        n = ctx.get("n")
        role = (ctx.get("role") or "member").strip().lower()

        template = sec.get("template_default", "{unit}{n}{role_suffix}")

        role_suffix_key = f"role_suffix_{role}"
        role_suffix = sec.get(role_suffix_key, sec.get("role_suffix_none", ""))

        n_str = "" if n is None else str(n).strip()

        callsign_raw = template.format(
            unit=unit,
            n=n_str,
            role_suffix=role_suffix,
        )

        return self._normalize_callsign(callsign_raw)
    def resolve_identity(self, ctx: Dict[str, Any]) -> Identity:
        # Policy grammar: derive default callsign/team/atak_role_type based on ctx + policy_id
        g = derive_grammar(self.policy_id, ctx)
        ctx = dict(ctx)

        # Only apply grammar defaults when ctx doesn't provide a non-empty override
        def _nonempty(v: Any) -> bool:
            try:
                return bool(str(v).strip())
            except Exception:
                return False

        if not _nonempty(ctx.get('callsign')) and _nonempty(g.get('callsign')):
            ctx['callsign'] = g.get('callsign')
        if not _nonempty(ctx.get('team')) and _nonempty(g.get('team')):
            ctx['team'] = g.get('team')
        if not _nonempty(ctx.get('atak_role_type')) and _nonempty(g.get('atak_role_type')):
            ctx['atak_role_type'] = g.get('atak_role_type')

        # Resolve TEAM: ctx.team override wins; else old mapping rules
        team_override = (str(ctx.get('team')).strip() if ctx.get('team') is not None else '')
        team = team_override if team_override else self.resolve_team(ctx)

        # Resolve CALLSIGN: ctx.callsign override wins (normalized); else old template rules
        callsign_override = (str(ctx.get('callsign')).strip() if ctx.get('callsign') is not None else '')
        callsign = self._normalize_callsign(callsign_override) if callsign_override else self.resolve_callsign(ctx)

        # Resolve ATAK role type: ctx.atak_role_type override wins; else policy defaults by role
        atak_role_type = None
        role = (ctx.get('role') or '').strip().lower()
        if role and 'role.defaults' in self.cfg:
            sec = self.cfg['role.defaults']
            if role in sec:
                atak_role_type = sec[role].strip() or None

        if ctx.get('atak_role_type'):
            atak_role_type = str(ctx.get('atak_role_type')).strip() or atak_role_type

        return Identity(callsign=callsign, team=team, atak_role_type=atak_role_type)
