from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from takctl.onboarding.models import OnboardingRecord, OnboardingStatus
from takctl.onboarding.store_filejson import FileJsonOnboardingStore, UserIdentity
from takctl.onboarding.user_directory_xml import UserDirectoryXml


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _age_human(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m, _ = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d{h}h"
    if h:
        return f"{h}h{m}m"
    return f"{m}m"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_or_none(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    try:
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        try:
            return str(dt)
        except Exception:
            return None


def _policy_id_from_ctx(ctx: Dict[str, Any]) -> Optional[str]:
    v = (ctx or {}).get("policy_id")
    return str(v) if v is not None and str(v).strip() else None


def _derive_if_missing(*, policy_id: Optional[str], ctx: Dict[str, Any], derived: Dict[str, Any]) -> Dict[str, Any]:
    """
    If stored derived identity is empty (older records), compute best-effort derived values
    from ctx + policy code.
    """
    if derived:
        return derived

    if not ctx:
        return {}

    try:
        from takctl.onboarding.policy import Policy  # local import to avoid startup coupling
        pol = Policy(policy_id)
        ident = pol.resolve_identity(ctx)

        out: Dict[str, Any] = {}
        for k in ("callsign", "team", "team_color", "atak_role_type"):
            v = getattr(ident, k, None)
            if v is not None:
                out[k] = v
        return out
    except Exception:
        return {}


def _build_identity(*, ident: Optional[UserIdentity]) -> Dict[str, Any]:
    """
    Canonical identity fields (TAKS + ATAK relevant).
    This is the ONE source for callsign/team/etc that will be pushed to config.pref.
    """
    if ident is None:
        return {
            "battalion": None,
            "unit": None,
            "company": None,
            "platoon": None,
            "squad": None,
            "role": None,
            "battalion_role": None,
            "callsign": None,
            "team": None,
            "team_color": None,
            "atak_role_type": None,
        }

    ctx = ident.ctx or {}
    policy_id = _policy_id_from_ctx(ctx)
    derived0 = ident.identity or {}
    derived = _derive_if_missing(policy_id=policy_id, ctx=ctx, derived=derived0)

    return {
        # TAKS structural concepts (policy-defined meaning)
        "battalion": ctx.get("battalion"),
        "unit": ctx.get("unit"),
        "company": ctx.get("company"),
        "platoon": ctx.get("platoon"),
        "squad": ctx.get("squad"),
        "role": ctx.get("role"),
        "battalion_role": ctx.get("battalion_role"),
        # ATAK / config.pref relevant concepts (canonical, single-valued)
        "callsign": derived.get("callsign"),
        "team": derived.get("team"),
        "team_color": derived.get("team_color"),
        "atak_role_type": derived.get("atak_role_type"),
    }


def _build_header(*, username: str, identity: Dict[str, Any], groups: List[str], policy_id: Optional[str]) -> Dict[str, Any]:
    """
    UI-ready short summary.
    NOTE: callsign here is the canonical callsign (same as identity.callsign).
    Observed CoT callsign belongs under activity.callsign only.
    """
    return {
        "username": username,
        "callsign": identity.get("callsign"),
        "unit": identity.get("unit") or identity.get("battalion"),
        "role": identity.get("role"),
        "atak_role_type": identity.get("atak_role_type"),
        "team": identity.get("team"),
        "team_color": identity.get("team_color"),
        "groups": list(groups),
        "policy_id": policy_id,
    }


def _build_authority(*, ident: Optional[UserIdentity]) -> Dict[str, Any]:
    """
    Keep this explicit; it matters for UI controls (editable/locked).
    """
    origin = getattr(ident, "origin", None) if ident is not None else None

    # Password "known to TAKS" should be true if either:
    #  - the model explicitly says password_known=True, OR
    #  - a password value exists in the identity record (common in our JSON store)
    password_known_flag = bool(getattr(ident, "password_known", False)) if ident is not None else False
    password_value_present = bool(getattr(ident, "password", None)) if ident is not None else False
    known_to_taks = bool(password_known_flag or password_value_present)

    overlay_present = ident is not None

    return {
        "tak_user": "marti_xml",
        "groups": {
            "authoritative": "marti_xml",
            "writable_by_taks": False,
            "notes": "Groups are currently observed from UserAuthenticationFile.xml; TAKS does not write them yet.",
        },
        "password": {
            "authoritative": "taks",
            "known_to_taks": known_to_taks,
        },
        "identity_overlay": {
            "present": overlay_present,
            "origin": origin,
        },
    }


    return {
        "tak_user": "marti_xml",
        "groups": {
            "authoritative": "marti_xml",
            "writable_by_taks": False,
            "notes": "Groups are currently observed from UserAuthenticationFile.xml; TAKS does not write them yet.",
        },
        "password": {
            "authoritative": "taks",
            "known_to_taks": password_known,
        },
        "identity": {
            "authoritative": "taks_overlay" if ident is not None else None,
            "overlay_present": ident is not None,
            "origin": origin,
        },
    }


def _build_onboarding_out(rec: Optional[OnboardingRecord]) -> Optional[Dict[str, Any]]:
    if rec is None:
        return None
    if hasattr(rec, "to_dict") and callable(getattr(rec, "to_dict")):
        # Ensure datetimes are already ISO in to_dict(); if not, callers will see them.
        return rec.to_dict()

    # Fallback minimal form (should rarely be used)
    out: Dict[str, Any] = {
        "username": rec.username,
        "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
        "package": None,
        "delivery": None,
    }
    pkg = getattr(rec, "package", None)
    if pkg is not None:
        out["package"] = {
            "package_type": getattr(pkg, "package_type", None),
            "version": getattr(pkg, "version", None),
            "generated_at": _iso_or_none(getattr(pkg, "generated_at", None)),
            "plugins": list(getattr(pkg, "plugins", []) or []),
            "maps": list(getattr(pkg, "maps", []) or []),
            "config_hash": getattr(pkg, "config_hash", None),
        }
    d = getattr(rec, "delivery", None)
    if d is not None:
        out["delivery"] = {
            "qr_generated": bool(getattr(d, "qr_generated", False)),
            "download_url": getattr(d, "download_url", None),
            "downloaded_at": _iso_or_none(getattr(d, "downloaded_at", None)),
            "delivery_method": getattr(d, "delivery_method", None),
        }
    return out


def _build_activity_out(act: Any, *, recent_minutes: int) -> Optional[Dict[str, Any]]:
    if act is None:
        return None

    now = datetime.now(timezone.utc)
    last_time_utc = _to_utc(act.last_time) if getattr(act, "last_time", None) is not None else None
    stale_utc = _to_utc(act.stale) if getattr(act, "stale", None) is not None else None
    age_sec = int((now - last_time_utc).total_seconds()) if last_time_utc else None

    return {
        "cot_seen": True,
        "uid": getattr(act, "uid", None),
        # Observed callsign (telemetry only; NOT identity)
        "callsign": getattr(act, "callsign", None),
        "last_cot_time": last_time_utc.isoformat() if last_time_utc else None,
        "stale": stale_utc.isoformat() if stale_utc else None,
        "is_current": bool(getattr(act, "is_current", False)),
        "age_sec": age_sec,
        "age_human": _age_human(age_sec) if isinstance(age_sec, int) else None,
        "recent_minutes": int(recent_minutes),
        "seen_recently": (age_sec is not None) and (age_sec <= (int(recent_minutes) * 60)),
    }


# ---------------------------------------------------------------------
# View Model
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class UserOnboardingView:
    username: str
    groups: List[str]
    onboarding_status: OnboardingStatus
    onboarding: Optional[OnboardingRecord]
    identity: Optional[UserIdentity]


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------

class OnboardingService:
    def __init__(self, ud: UserDirectoryXml, store: FileJsonOnboardingStore):
        self.ud = ud
        self.store = store

    def list_users_with_onboarding(self) -> List[UserOnboardingView]:
        users = self.ud.list_users()
        records = {r.username: r for r in self.store.list_records()}

        out: List[UserOnboardingView] = []
        for u in users:
            rec = records.get(u.username)
            status = rec.status if rec is not None else OnboardingStatus.NEW
            ident = self.store.get_identity(u.username)
            out.append(
                UserOnboardingView(
                    username=u.username,
                    groups=list(u.groups),
                    onboarding_status=status,
                    onboarding=rec,
                    identity=ident,
                )
            )
        return out

    def status(self, db=None, unknown_limit: int = 50, recent_minutes: int = 120) -> Dict[str, Any]:
        rows = self.list_users_with_onboarding()
        known_usernames = [r.username for r in rows]

        activity_map: Dict[str, Any] = {}
        unknown: List[Dict[str, Any]] = []

        if db is not None:
            from takctl.onboarding.activity_pg import fetch_activity_for_usernames, fetch_unknown_endpoints
            activity_map = fetch_activity_for_usernames(db, known_usernames)
            unknown = fetch_unknown_endpoints(db, known_usernames, limit=unknown_limit)

        users_out: List[Dict[str, Any]] = []

        for r in rows:
            ident = r.identity
            ctx = (ident.ctx or {}) if ident is not None else {}
            policy_id = _policy_id_from_ctx(ctx)

            identity = _build_identity(ident=ident)
            header = _build_header(
                username=r.username,
                identity=identity,
                groups=list(r.groups),
                policy_id=policy_id,
            )

            user_out: Dict[str, Any] = {
                "header": header,
                "identity": identity,
                "marti": {"groups": list(r.groups)},
                "policy": {"id": policy_id},
                "authority": _build_authority(ident=ident),
                "onboarding_status": r.onboarding_status.value,
                "onboarding": _build_onboarding_out(r.onboarding),
                "activity": _build_activity_out(activity_map.get(r.username), recent_minutes=int(recent_minutes)),
                # Selection is per-user; for list view keep it out (heavy / noisy)
                "selection": None,
            }

            users_out.append(user_out)

        # Summary
        total_users = len(users_out)
        cot_seen = sum(1 for u in users_out if u.get("activity") is not None)
        never_seen = total_users - cot_seen
        seen_recently = sum(1 for u in users_out if (u.get("activity") or {}).get("seen_recently") is True)
        is_current = sum(1 for u in users_out if (u.get("activity") or {}).get("is_current") is True)

        # Unknown endpoints summary is best-effort (depends on DB query output)
        unknown_out: List[Dict[str, Any]] = []
        for e in unknown:
            out_e = dict(e)
            last_time = e.get("last_cot_time")
            stale = e.get("stale")
            # normalize datetimes if present
            if isinstance(last_time, datetime):
                out_e["last_cot_time"] = _to_utc(last_time).isoformat()
            if isinstance(stale, datetime):
                out_e["stale"] = _to_utc(stale).isoformat()
            unknown_out.append(out_e)

        unknown_seen_recently = 0
        for e in unknown_out:
            if e.get("seen_recently") is True:
                unknown_seen_recently += 1

        return {
            "summary": {
                "total_users": total_users,
                "cot_seen": cot_seen,
                "never_seen": never_seen,
                "seen_recently": seen_recently,
                "is_current": is_current,
                "unknown_endpoints": len(unknown_out),
                "unknown_seen_recently": unknown_seen_recently,
                "recent_minutes": int(recent_minutes),
            },
            "users": users_out,
            "unknown_endpoints": unknown_out,
        }

    def user_card(self, *, username: str, db=None, recent_minutes: int = 120) -> dict:
        """
        Single canonical card model.

        Order is intentional:
          header -> identity -> marti -> policy -> authority -> onboarding -> activity -> selection
        """
        from takctl.onboarding.selection import load_selection
        from takctl.onboarding.activity_pg import fetch_activity_for_usernames

        u = self.ud.get_user(username)
        if u is None:
            raise KeyError(username)

        rec = self.store.get_record(username)
        ident = self.store.get_identity(username)
        sel = load_selection(username) or None

        # Optional activity
        act = None
        if db is not None:
            try:
                m = fetch_activity_for_usernames(db, [username])
                act = m.get(username)
            except Exception:
                act = None

        ctx = (ident.ctx or {}) if ident is not None else {}
        policy_id = _policy_id_from_ctx(ctx)

        identity = _build_identity(ident=ident)
        header = _build_header(
            username=username,
            identity=identity,
            groups=list(u.groups),
            policy_id=policy_id,
        )

        card = {
            "header": header,
            "identity": identity,
            "marti": {"groups": list(u.groups)},
            "policy": {"id": policy_id},
            "authority": _build_authority(ident=ident),
            "onboarding": _build_onboarding_out(rec),
            "activity": _build_activity_out(act, recent_minutes=int(recent_minutes)),
            "selection": sel,
        }

        return card
