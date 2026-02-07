from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from takctl.onboarding.models import OnboardingRecord, OnboardingStatus
from takctl.onboarding.store_filejson import FileJsonOnboardingStore
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
            out.append(
                UserOnboardingView(
                    username=u.username,
                    groups=list(u.groups),
                    onboarding_status=status,
                    onboarding=rec,
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
            user_out: Dict[str, Any] = {
                "username": r.username,
                "groups": list(r.groups),
                "onboarding_status": r.onboarding_status.value,
                "onboarding": r.onboarding.to_dict() if r.onboarding is not None else None,
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

