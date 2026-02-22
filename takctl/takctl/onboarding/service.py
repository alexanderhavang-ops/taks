from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from takctl.onboarding.models import OnboardingRecord, OnboardingStatus
from takctl.onboarding.store_filejson import FileJsonOnboardingStore, UserIdentity
from takctl.onboarding.user_directory_xml import UserDirectoryXml


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


@dataclass(frozen=True)
class UserOnboardingView:
    username: str
    groups: List[str]
    onboarding_status: OnboardingStatus
    onboarding: Optional[OnboardingRecord]
    identity: Optional[UserIdentity]


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

        now = datetime.now(timezone.utc)
        users_out: List[Dict[str, Any]] = []

        for r in rows:
            ident = r.identity
            ident_out = None
            if ident is not None:
                ident_out = {
                    "origin": ident.origin,
                    "ctx": ident.ctx or {},
                    "identity": ident.identity or {},
                    "password_known": bool(ident.password_known),
                    # NOTE: never include password in status listing; card/token decides reveal.
                }

            user_out: Dict[str, Any] = {
                "username": r.username,
                "groups": list(r.groups),
                "onboarding_status": r.onboarding_status.value,
                "onboarding": r.onboarding.to_dict() if r.onboarding is not None else None,
                "taks_identity": ident_out,
                "activity": None,
            }

            act = activity_map.get(r.username)
            if act is not None:
                last_time_utc = _to_utc(act.last_time)
                stale_utc = _to_utc(act.stale)
                age_sec = int((now - last_time_utc).total_seconds())

                user_out["activity"] = {
                    "cot_seen": True,
                    "uid": act.uid,
                    "callsign": act.callsign,
                    "last_cot_time": last_time_utc.isoformat(),
                    "stale": stale_utc.isoformat(),
                    "is_current": bool(act.is_current),
                    "age_sec": age_sec,
                    "age_human": _age_human(age_sec),
                    "recent_minutes": int(recent_minutes),
                    "seen_recently": age_sec <= (int(recent_minutes) * 60),
                }

            users_out.append(user_out)

        unknown_out: List[Dict[str, Any]] = []
        for e in unknown:
            last_time = e.get("last_cot_time")
            stale = e.get("stale")
            try:
                last_dt = _to_utc(last_time) if isinstance(last_time, datetime) else None
                stale_dt = _to_utc(stale) if isinstance(stale, datetime) else None
                age_sec = int((now - last_dt).total_seconds()) if last_dt else None
            except Exception:
                last_dt = None
                stale_dt = None
                age_sec = None

            out_e = dict(e)
            if last_dt is not None:
                out_e["last_cot_time"] = last_dt.isoformat()
            if stale_dt is not None:
                out_e["stale"] = stale_dt.isoformat()
            if age_sec is not None:
                out_e["age_sec"] = age_sec
                out_e["age_human"] = _age_human(age_sec)
                out_e["recent_minutes"] = int(recent_minutes)
                out_e["seen_recently"] = age_sec <= (int(recent_minutes) * 60)
            else:
                out_e.setdefault("seen_recently", None)

            unknown_out.append(out_e)

        total_users = len(users_out)
        cot_seen = sum(1 for u in users_out if u.get("activity") is not None)
        never_seen = total_users - cot_seen
        seen_recently = sum(1 for u in users_out if (u.get("activity") or {}).get("seen_recently") is True)
        is_current = sum(1 for u in users_out if (u.get("activity") or {}).get("is_current") is True)

        unknown_count = len(unknown_out)
        unknown_seen_recently = sum(1 for e in unknown_out if e.get("seen_recently") is True)

        return {
            "summary": {
                "total_users": total_users,
                "cot_seen": cot_seen,
                "never_seen": never_seen,
                "seen_recently": seen_recently,
                "is_current": is_current,
                "unknown_endpoints": unknown_count,
                "unknown_seen_recently": unknown_seen_recently,
                "recent_minutes": int(recent_minutes),
            },
            "users": users_out,
            "unknown_endpoints": unknown_out,
        }

    def user_card(self, *, username: str, db=None, recent_minutes: int = 120) -> dict:
        """Return a JSON-friendly single-user card model.

        Layers (keep them separate for UI sanity):
          - tak_user: observed from UserAuthenticationFile.xml (external truth)
          - taks_identity: optional persisted TAKS identity record (origin=taks|marti)
          - selection: last chosen inputs on Generate page (policy ctx + endpoints)
          - onboarding: persisted stage gates + package + delivery (takctl-owned)
          - activity: CoT correlation from DB (optional)
        """

        from datetime import datetime, timezone
        from takctl.onboarding.selection import load_selection
        from takctl.onboarding.activity_pg import fetch_activity_for_usernames

        def _to_utc(dt):
            if dt is None:
                return None
            if getattr(dt, "tzinfo", None) is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

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

        u = self.ud.get_user(username)
        if u is None:
            raise KeyError(username)

        # Persisted state
        rec = self.store.get_record(username)
        ident = self.store.get_identity(username)
        sel = load_selection(username) or {}

        # Activity (optional)
        activity_out = None
        if db is not None:
            try:
                m = fetch_activity_for_usernames(db, [username])
                act = m.get(username)
            except Exception:
                act = None
            if act is not None:
                now = datetime.now(timezone.utc)
                last_time_utc = _to_utc(act.last_time)
                stale_utc = _to_utc(act.stale)
                age_sec = int((now - last_time_utc).total_seconds()) if last_time_utc else 0
                activity_out = {
                    "cot_seen": True,
                    "uid": act.uid,
                    "callsign": act.callsign,
                    "last_cot_time": last_time_utc.isoformat() if last_time_utc else None,
                    "stale": stale_utc.isoformat() if stale_utc else None,
                    "is_current": bool(act.is_current),
                    "age_sec": age_sec,
                    "age_human": _age_human(age_sec),
                    "recent_minutes": int(recent_minutes),
                    "seen_recently": age_sec <= (int(recent_minutes) * 60),
                }

        taks_identity_out = None
        if ident is not None:
            taks_identity_out = {
                "origin": ident.origin,
                "ctx": ident.ctx or {},
                "identity": ident.identity or {},
                "password_known": bool(ident.password_known),
                # NOTE: password reveal is via card/token, never in card.json by default
            }

        onboarding_out = None
        if rec is not None:
            # prefer model serializer if present; otherwise fall back to store JSON form
            if hasattr(rec, "to_dict") and callable(getattr(rec, "to_dict")):
                onboarding_out = rec.to_dict()
            else:
                onboarding_out = {
                    "username": rec.username,
                    "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
                    "package": None,
                    "delivery": None,
                }
                if rec.package is not None:
                    onboarding_out["package"] = {
                        "package_type": rec.package.package_type,
                        "version": rec.package.version,
                        "generated_at": getattr(rec.package.generated_at, "isoformat", lambda: str(rec.package.generated_at))(),
                        "plugins": list(rec.package.plugins),
                        "maps": list(rec.package.maps),
                        "config_hash": rec.package.config_hash,
                    }
                if rec.delivery is not None:
                    onboarding_out["delivery"] = {
                        "qr_generated": bool(rec.delivery.qr_generated),
                        "download_url": rec.delivery.download_url,
                        "downloaded_at": getattr(rec.delivery.downloaded_at, "isoformat", lambda: str(rec.delivery.downloaded_at))() if rec.delivery.downloaded_at else None,
                        "delivery_method": rec.delivery.delivery_method,
                    }

        return {
            "tak_user": {
                "username": u.username,
                "groups": list(u.groups),
            },
            "taks_identity": taks_identity_out,
            "selection": sel,
            "onboarding": onboarding_out,
            "activity": activity_out,
        }
