from __future__ import annotations

import re
import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from takctl.config import load_config
from takctl.onboarding.identity_grammar import derive_grammar
from takctl.onboarding.fal import derive_fal_ctx
from takctl.onboarding.policy_registry import get_policy


@dataclass(frozen=True)
class Identity:
    callsign: str
    team: str
    atak_role_type: Optional[str] = None

    # read-only debug/preview fields for UI
    callsign_variants: Optional[Dict[str, str]] = None
    callsign_policy_effective: Optional[str] = None


class PolicyError(RuntimeError):
    pass


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


class Policy:
    """
    Legacy policy.conf loader with JSON-policy fallback.

    Resolution order for legacy config:
      1) policy_dir from runtime conf.d (if set)
      2) /opt/tak/policies/<id>/policy.conf
      3) /opt/taks/policies/<id>/policy.conf

    JSON metadata fallback:
      - onboarding policy_registry builtin/runtime policy.json
    """

    def __init__(self, policy_id: Optional[str] = None) -> None:
        cfg0 = load_config()
        self.policy_id = str(policy_id or cfg0.get("default_policy_id", "") or "").strip()
        if not self.policy_id:
            raise PolicyError("default_policy_id is empty in runtime conf.d")

        self.path = self._resolve_path(self.policy_id)

        self.cfg = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
        if self.path:
            self.cfg.read(self.path, encoding="utf-8")

        self.json_meta: Dict[str, Any] = {}
        try:
            j = get_policy(self.policy_id)
            if isinstance(j, dict):
                self.json_meta = j
        except Exception:
            self.json_meta = {}

        if not self.path and not self.json_meta:
            raise PolicyError(
                f"policy not found for policy_id={self.policy_id!r}. "
                f"Tried legacy policy.conf paths and policy_registry JSON."
            )

    @staticmethod
    def _resolve_path(policy_id: str) -> str:
        cfg0 = load_config()
        base = str(cfg0.get("policy_dir", "") or "").strip()
        candidates = []

        here = Path(__file__).resolve()
        pkg_root = here.parents[2]
        repo_root = here.parents[3] if len(here.parents) > 3 else pkg_root.parent

        if base:
            candidates.append(Path(base) / policy_id / "policy.conf")
            candidates.append(Path(base) / f"{policy_id}.conf")
            candidates.append(Path(base) / "policy.conf")

        candidates.extend(
            [
                Path("/opt/tak/policies") / policy_id / "policy.conf",
                Path("/opt/taks/policies") / policy_id / "policy.conf",
                pkg_root / "policies" / policy_id / "policy.conf",
                repo_root / "policies" / policy_id / "policy.conf",
            ]
        )

        seen = set()
        for p in candidates:
            sp = str(p)
            if sp in seen:
                continue
            seen.add(sp)
            try:
                if p.is_file():
                    return sp
            except Exception:
                continue

        return ""

    def meta(self) -> Dict[str, str]:
        if "meta" in self.cfg:
            d = dict(self.cfg["meta"])
            d.setdefault("id", self.policy_id)
            return d

        d: Dict[str, str] = {"id": self.policy_id}
        if self.json_meta:
            if self.json_meta.get("name"):
                d["name"] = str(self.json_meta.get("name") or "").strip()
            if self.json_meta.get("title"):
                d["title"] = str(self.json_meta.get("title") or "").strip()
            if self.json_meta.get("version"):
                d["version"] = str(self.json_meta.get("version") or "").strip()
        return d

    def _normalize_callsign(self, s: str) -> str:
        sec = self.cfg["callsign"] if "callsign" in self.cfg else {}
        if sec.get("strip_spaces", "false").lower() in ("1", "true", "yes", "on"):
            s = s.replace(" ", "")
        if sec.get("normalize_upper", "false").lower() in ("1", "true", "yes", "on"):
            s = s.upper()
        s = re.sub(r"[^A-Z0-9_\-]", "", s)
        return s

    def resolve_team(self, ctx: Dict[str, Any]) -> str:
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

    def resolve_callsign(self, ctx: Dict[str, Any]) -> str:
        sec = self.cfg["callsign"] if "callsign" in self.cfg else {}
        unit = (ctx.get("unit") or "").strip()
        n = ctx.get("n")
        role = (ctx.get("role") or "member").strip().lower()

        template = sec.get("template_default", "{unit}{n}{role_suffix}")

        role_suffix_key = f"role_suffix_{role}"
        role_suffix = sec.get(role_suffix_key, sec.get("role_suffix_none", ""))

        n_str = "" if n is None else str(n).strip()

        fmt = dict(ctx or {})
        fmt.setdefault("unit", unit)
        fmt.setdefault("n", n_str)
        fmt.setdefault("role", role)
        fmt.setdefault("role_suffix", role_suffix)

        callsign_raw = template.format_map(_SafeFormatDict(fmt))
        return self._normalize_callsign(callsign_raw)

    def resolve_identity(self, ctx: Dict[str, Any]) -> Identity:
        ctx = dict(ctx or {})

        try:
            derived = derive_fal_ctx(self.cfg, ctx)
            for k, v in derived.items():
                if k not in ctx or not str(ctx.get(k) or "").strip():
                    ctx[k] = v
        except Exception:
            pass

        g = derive_grammar(self.policy_id, ctx)
        if not isinstance(g, dict) or not g.get("callsign"):
            raise RuntimeError("Grammar did not produce callsign")

        def _nonempty(v: Any) -> bool:
            try:
                return bool(str(v).strip())
            except Exception:
                return False

        if not _nonempty(ctx.get("team")) and _nonempty(g.get("team")):
            ctx["team"] = g.get("team")
        if not _nonempty(ctx.get("atak_role_type")) and _nonempty(g.get("atak_role_type")):
            ctx["atak_role_type"] = g.get("atak_role_type")

        callsign = self._normalize_callsign(str(g.get("callsign") or ""))

        team_override = (str(ctx.get("team")).strip() if ctx.get("team") is not None else "")
        team = team_override if team_override else self.resolve_team(ctx)

        atak_role_type = None
        role = (ctx.get("role") or "").strip().lower()
        if role and "role.defaults" in self.cfg:
            sec = self.cfg["role.defaults"]
            if role in sec:
                atak_role_type = sec[role].strip() or None

        if ctx.get("atak_role_type"):
            atak_role_type = str(ctx.get("atak_role_type")).strip() or atak_role_type

        variants = g.get("callsign_variants") if isinstance(g.get("callsign_variants"), dict) else None
        eff = g.get("callsign_policy_effective")
        eff = str(eff).strip() if eff else None

        return Identity(
            callsign=callsign,
            team=team,
            atak_role_type=atak_role_type,
            callsign_variants=variants,
            callsign_policy_effective=eff,
        )
