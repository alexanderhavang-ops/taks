from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from takctl.onboarding.models import OnboardingRecord, OnboardingStatus
from takctl.onboarding.store_filejson import FileJsonOnboardingStore, UserIdentity
from takctl.onboarding.user_directory_xml import UserDirectoryXml
from takctl.onboarding.activity_pg import (
    fetch_devices_for_usernames,
    fetch_unknown_endpoints,
)
from takctl.services.mumble_live import snapshot_mumble_live
from takctl.services.mumble_match import build_voice_assignment


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
    if derived:
        return derived
    if not ctx:
        return {}

    try:
        from takctl.onboarding.policy import Policy
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
        "battalion": ctx.get("battalion"),
        "unit": ctx.get("unit") or ctx.get("battalion"),
        "company": ctx.get("company"),
        "platoon": ctx.get("platoon"),
        "squad": ctx.get("squad"),
        "role": ctx.get("role"),
        "battalion_role": ctx.get("battalion_role"),
        "callsign": derived.get("callsign"),
        "team": derived.get("team"),
        "team_color": derived.get("team_color"),
        "atak_role_type": derived.get("atak_role_type"),
    }


def _build_header(*, username: str, identity: Dict[str, Any], groups: List[str], policy_id: Optional[str]) -> Dict[str, Any]:
    return {
        "username": username,
        "callsign": identity.get("callsign") or username,
        "unit": identity.get("unit") or identity.get("battalion"),
        "role": identity.get("role"),
        "atak_role_type": identity.get("atak_role_type"),
        "team": identity.get("team"),
        "team_color": identity.get("team_color"),
        "groups": list(groups),
        "policy_id": policy_id,
    }


def _build_authority(*, ident: Optional[UserIdentity]) -> Dict[str, Any]:
    origin = getattr(ident, "origin", None) if ident is not None else None
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


def _status_value(rec: Optional[OnboardingRecord]) -> Optional[str]:
    if rec is None:
        return None
    st = getattr(rec, "status", None)
    if st is None:
        return None
    return st.value if hasattr(st, "value") else str(st)


def _is_offboarded(rec: Optional[OnboardingRecord]) -> bool:
    if rec is None:
        return False
    if bool(getattr(rec, "offboarded", False)):
        return True
    st = _status_value(rec) or ""
    return st.lower() in ("offboarded", "retired", "disabled", "revoked")


def _artifact_evidence(*, username: str) -> Dict[str, Any]:
    try:
        from pathlib import Path
        root = Path("/opt/tak/takctl-state/onboarding/artifacts") / username
        present = root.exists()

        def _exists(p: str) -> bool:
            return (root / p).exists()

        any_qr = False
        if present:
            for pat in ("*.png", "*.PNG"):
                if list(root.glob(pat)):
                    any_qr = True
                    break

        return {
            "artifacts_root": str(root),
            "present": bool(present),
            "atak_package_zip": bool(_exists("atak/package.zip") or _exists("package.zip")),
            "atak_package_creds_zip": bool(_exists("atak/package-creds.zip") or _exists("package-creds.zip")),
            "any_qr_png": bool(any_qr),
        }
    except Exception:
        return {"present": False}


def _db_fetchall(db: Any, sql: str, params: tuple) -> list[Any]:
    if db is None:
        return []
    if hasattr(db, "fetchall") and callable(getattr(db, "fetchall")):
        rows = db.fetchall(sql, params)
        return list(rows or [])
    if hasattr(db, "query") and callable(getattr(db, "query")):
        rows = db.query(sql, params)
        return list(rows or [])
    cur = db.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    return list(rows)


def _row_get(row: Any, idx: int, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[idx]


def _fetch_user_dn_cert_summary(db: Any, username: str) -> Dict[str, Any]:
    if db is None:
        return {
            "count": 0,
            "revoked_count": 0,
            "latest_cert": None,
        }

    sql = """
SELECT
  id,
  user_dn,
  client_uid,
  issuance_date,
  effective_date,
  expiration_date,
  revocation_date
FROM public.certificate
WHERE user_dn = %s
ORDER BY issuance_date DESC NULLS LAST, id DESC
;
"""
    rows = _db_fetchall(db, sql, (username,))
    revoked = 0
    latest_cert = None

    for i, row in enumerate(rows):
        revocation_date = _row_get(row, 6, "revocation_date")
        if revocation_date is not None:
            revoked += 1
        if i == 0:
            latest_cert = {
                "id": _row_get(row, 0, "id"),
                "client_uid": _row_get(row, 2, "client_uid"),
                "issuance_date": _iso_or_none(_row_get(row, 3, "issuance_date")),
                "effective_date": _iso_or_none(_row_get(row, 4, "effective_date")),
                "expiration_date": _iso_or_none(_row_get(row, 5, "expiration_date")),
                "revocation_date": _iso_or_none(revocation_date),
            }

    return {
        "count": len(rows),
        "revoked_count": revoked,
        "latest_cert": latest_cert,
    }


def _build_activity_from_devices(devices: list[dict[str, Any]], *, recent_minutes: int) -> Optional[Dict[str, Any]]:
    best = None
    for d in devices or []:
        if not d.get("last_cot_time"):
            continue
        if best is None or str(d.get("last_cot_time") or "") > str(best.get("last_cot_time") or ""):
            best = d

    if best is None:
        return None

    return {
        "cot_seen": True,
        "uid": best.get("client_uid"),
        "callsign": best.get("observed_callsign"),
        "last_cot_time": best.get("last_cot_time"),
        "last_seen": best.get("last_cot_time"),
        "stale": best.get("stale"),
        "is_current": bool(best.get("is_current")),
        "age_sec": best.get("age_sec"),
        "age_human": best.get("age_human"),
        "recent_minutes": int(recent_minutes),
        "seen_recently": bool(best.get("seen_recently")),
    }


def _build_marti_client_summary(*, username: str, devices: list[dict[str, Any]], cert_summary: Dict[str, Any]) -> Dict[str, Any]:
    endpoint_uids = []
    seen = set()
    for d in devices or []:
        uid = str(d.get("client_uid") or "").strip()
        if uid and uid not in seen:
            endpoint_uids.append(uid)
            seen.add(uid)

    latest_endpoint = None
    if devices:
        d0 = devices[0]
        latest_endpoint = {
            "id": d0.get("endpoint_id"),
            "callsign": d0.get("observed_callsign"),
            "uid": d0.get("client_uid"),
            "username": username,
        }

    latest_event_device = None
    for d in devices or []:
        if not d.get("last_event_time"):
            continue
        if latest_event_device is None or str(d.get("last_event_time") or "") > str(latest_event_device.get("last_event_time") or ""):
            latest_event_device = d

    latest_endpoint_event = None
    if latest_event_device is not None:
        latest_endpoint_event = {
            "client_endpoint_id": latest_event_device.get("endpoint_id"),
            "created_ts": latest_event_device.get("last_event_time"),
            "connection_event_type_id": latest_event_device.get("connection_event_type_id"),
            "client_version": latest_event_device.get("client_version"),
            "client_platform": latest_event_device.get("client_platform"),
            "client_product": latest_event_device.get("client_product"),
            "tak_platform": latest_event_device.get("tak_platform"),
            "tak_version": latest_event_device.get("tak_version"),
            "tak_device": latest_event_device.get("tak_device"),
            "tak_os": latest_event_device.get("tak_os"),
        }

    certs_by_client_uid_n = 0
    certs_revoked_n = 0
    has_certificate = False
    for d in devices or []:
        certs_by_client_uid_n += int(d.get("certs_n") or 0)
        certs_revoked_n += int(d.get("revoked_certs_n") or 0)
        if int(d.get("certs_n") or 0) > 0:
            has_certificate = True

    if int(cert_summary.get("count") or 0) > 0:
        has_certificate = True

    return {
        "db_used": True,
        "endpoints_n": len(devices or []),
        "endpoint_uids": endpoint_uids,
        "latest_endpoint": latest_endpoint,
        "latest_endpoint_event": latest_endpoint_event,
        "certs_by_user_dn_n": int(cert_summary.get("count") or 0),
        "certs_by_client_uid_n": certs_by_client_uid_n,
        "certs_revoked_n": certs_revoked_n,
        "latest_cert": cert_summary.get("latest_cert"),
        "has_endpoint": len(devices or []) > 0,
        "has_endpoint_event": latest_endpoint_event is not None,
        "has_certificate": has_certificate,
    }


def _build_onboarding_out(rec: Optional[OnboardingRecord]) -> Optional[Dict[str, Any]]:
    if rec is None:
        return None

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


def _compute_lifecycle(
    *,
    username: str,
    ident: Optional[UserIdentity],
    selection: Any,
    rec: Optional[OnboardingRecord],
    activity: Optional[Dict[str, Any]],
    marti_client: Dict[str, Any],
) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {
        "username": username,
        "taks_identity_present": ident is not None,
        "taks_origin": getattr(ident, "origin", None) if ident is not None else None,
        "taks_password_known": bool(
            getattr(ident, "password_known", False) or getattr(ident, "password", None)
        ) if ident is not None else False,
        "selection_present": selection is not None,
        "onboarding_status": _status_value(rec),
        "offboarded": _is_offboarded(rec),
        "cot_seen": bool((activity or {}).get("cot_seen")) if activity is not None else False,
        "seen_recently": bool((activity or {}).get("seen_recently")) if activity is not None else False,
        "marti_client": marti_client or {},
        "artifacts": _artifact_evidence(username=username),
    }

    created_by_taks = (evidence["taks_origin"] == "taks")
    cot_seen = bool(evidence["cot_seen"])
    has_cert = bool((marti_client or {}).get("has_certificate"))
    has_endpoint = bool((marti_client or {}).get("has_endpoint"))
    has_endpoint_event = bool((marti_client or {}).get("has_endpoint_event"))

    if evidence["offboarded"]:
        stage = "SG4"
        label = "Offboarded"
    elif not created_by_taks:
        stage = "SG0"
        label = "External user (not created by TAKS)"
    else:
        if cot_seen or has_endpoint_event:
            stage = "SG3"
            label = "Active"
        elif has_cert or has_endpoint:
            stage = "SG2"
            label = "Enrolled"
        else:
            stage = "SG1"
            label = "Created by TAKS"

    return {"stage": stage, "label": label, "evidence": evidence}


def _build_voice_for_user(
    *,
    username: str,
    header_callsign: str,
    devices: List[Dict[str, Any]],
    mumble_snapshot: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot = dict(mumble_snapshot or {})
    try:
        return build_voice_assignment(
            username=username,
            header_callsign=header_callsign,
            devices=list(devices or []),
            mumble_snapshot=snapshot,
        )
    except Exception as e:
        server = dict(snapshot.get("server") or {})
        meta = dict(snapshot.get("meta") or {})
        return {
            "ok": False,
            "username": str(username or "").strip(),
            "server": {
                "host": server.get("host"),
                "port": server.get("port"),
                "connected": bool(server.get("connected")),
            },
            "snapshot_meta": {
                "source": str(meta.get("source") or "takctl.services.mumble_live"),
                "generated_at": meta.get("generated_at"),
            },
            "error": f"voice assignment failed: {type(e).__name__}: {e}",
            "user": {
                "callsign": str(header_callsign or "").strip(),
                "connected_now": False,
                "channel_names": [],
                "matched_user_names": [],
                "header_matches": [],
            },
            "devices": [],
            "raw_counts": {
                "channels": len(list(snapshot.get("channels") or [])),
                "users": len(list(snapshot.get("users") or [])),
                "devices": len(list(devices or [])),
            },
        }


def _build_voice_summary(voice: Dict[str, Any]) -> Dict[str, Any]:
    server = dict((voice or {}).get("server") or {})
    raw_counts = dict((voice or {}).get("raw_counts") or {})
    user = dict((voice or {}).get("user") or {})
    header_matches = list(user.get("header_matches") or [])

    matched_connected_users = sum(1 for m in header_matches if bool(m.get("connected_now")))

    return {
        "server": {
            "host": server.get("host"),
            "port": server.get("port"),
            "connected": bool(server.get("connected")),
        },
        "live_users": int(raw_counts.get("users") or 0),
        "matched_connected_users": int(matched_connected_users),
    }


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
        out.sort(key=lambda x: x.username.lower())
        return out

    def status(self, db=None, unknown_limit: int = 50, recent_minutes: int = 120) -> Dict[str, Any]:
        rows = self.list_users_with_onboarding()
        usernames = [r.username for r in rows]

        devices_map: Dict[str, list[dict[str, Any]]] = {}
        unknown: List[Dict[str, Any]] = []
        cert_summaries: Dict[str, Dict[str, Any]] = {}

        if db is not None:
            devices_map = fetch_devices_for_usernames(db, usernames, recent_minutes=int(recent_minutes))
            unknown = fetch_unknown_endpoints(
                db,
                usernames,
                limit=int(unknown_limit),
                recent_minutes=int(recent_minutes),
            )
            for username in usernames:
                cert_summaries[username] = _fetch_user_dn_cert_summary(db, username)
        else:
            cert_summaries = {username: {"count": 0, "revoked_count": 0, "latest_cert": None} for username in usernames}

        try:
            mumble_snapshot = snapshot_mumble_live()
        except Exception as e:
            mumble_snapshot = {
                "meta": {"source": "takctl.services.mumble_live"},
                "server": {"host": None, "port": None, "connected": False},
                "channels": [],
                "users": [],
                "error": f"snapshot failed: {type(e).__name__}: {e}",
            }

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

            devices = list(devices_map.get(r.username) or [])
            activity = _build_activity_from_devices(devices, recent_minutes=int(recent_minutes))
            cert_summary = cert_summaries.get(r.username) or {"count": 0, "revoked_count": 0, "latest_cert": None}
            marti_client = _build_marti_client_summary(
                username=r.username,
                devices=devices,
                cert_summary=cert_summary,
            ) if db is not None else {
                "db_used": False,
                "endpoints_n": 0,
                "endpoint_uids": [],
                "latest_endpoint": None,
                "latest_endpoint_event": None,
                "certs_by_user_dn_n": 0,
                "certs_by_client_uid_n": 0,
                "certs_revoked_n": 0,
                "latest_cert": None,
                "has_endpoint": False,
                "has_endpoint_event": False,
                "has_certificate": False,
            }

            lifecycle = _compute_lifecycle(
                username=r.username,
                ident=ident,
                selection=None,
                rec=r.onboarding,
                activity=activity,
                marti_client=marti_client,
            )

            voice = _build_voice_for_user(
                username=r.username,
                header_callsign=str(header.get("callsign") or r.username),
                devices=devices,
                mumble_snapshot=mumble_snapshot,
            )
            voice_summary = _build_voice_summary(voice)

            users_out.append(
                {
                    "header": header,
                    "identity": identity,
                    "marti": {"groups": list(r.groups), "client": marti_client},
                    "policy": {"id": policy_id},
                    "authority": _build_authority(ident=ident),
                    "lifecycle": lifecycle,
                    "onboarding_status": r.onboarding_status.value,
                    "onboarding": _build_onboarding_out(r.onboarding),
                    "activity": activity,
                    "devices": devices,
                    "selection": None,
                    "voice": voice,
                    "voice_summary": voice_summary,
                }
            )

        total_users = len(users_out)
        cot_seen = sum(1 for u in users_out if u.get("activity") is not None)
        never_seen = total_users - cot_seen
        seen_recently = sum(1 for u in users_out if (u.get("activity") or {}).get("seen_recently") is True)
        is_current = sum(1 for u in users_out if (u.get("activity") or {}).get("is_current") is True)
        unknown_seen_recently = sum(1 for e in unknown if e.get("seen_recently") is True)
        voice_connected_now = sum(1 for u in users_out if bool(((u.get("voice") or {}).get("user") or {}).get("connected_now")))

        return {
            "summary": {
                "total_users": total_users,
                "cot_seen": cot_seen,
                "never_seen": never_seen,
                "seen_recently": seen_recently,
                "is_current": is_current,
                "unknown_endpoints": len(unknown),
                "unknown_seen_recently": unknown_seen_recently,
                "recent_minutes": int(recent_minutes),
                "voice_connected_now": voice_connected_now,
            },
            "users": users_out,
            "unknown_endpoints": unknown,
        }

    def user_card(self, *, username: str, db=None, recent_minutes: int = 120) -> dict:
        from takctl.onboarding.selection import load_selection

        u = self.ud.get_user(username)
        if u is None:
            raise KeyError(username)

        rec = self.store.get_record(username)
        ident = self.store.get_identity(username)
        sel = load_selection(username) or None

        devices = []
        cert_summary = {"count": 0, "revoked_count": 0, "latest_cert": None}
        if db is not None:
            devices = fetch_devices_for_usernames(db, [username], recent_minutes=int(recent_minutes)).get(username, [])
            cert_summary = _fetch_user_dn_cert_summary(db, username)

        activity = _build_activity_from_devices(devices, recent_minutes=int(recent_minutes))
        marti_client = _build_marti_client_summary(
            username=username,
            devices=devices,
            cert_summary=cert_summary,
        ) if db is not None else {
            "db_used": False,
            "endpoints_n": 0,
            "endpoint_uids": [],
            "latest_endpoint": None,
            "latest_endpoint_event": None,
            "certs_by_user_dn_n": 0,
            "certs_by_client_uid_n": 0,
            "certs_revoked_n": 0,
            "latest_cert": None,
            "has_endpoint": False,
            "has_endpoint_event": False,
            "has_certificate": False,
        }

        ctx = (ident.ctx or {}) if ident is not None else {}
        policy_id = _policy_id_from_ctx(ctx)
        identity = _build_identity(ident=ident)
        header = _build_header(
            username=username,
            identity=identity,
            groups=list(u.groups),
            policy_id=policy_id,
        )

        lifecycle = _compute_lifecycle(
            username=username,
            ident=ident,
            selection=sel,
            rec=rec,
            activity=activity,
            marti_client=marti_client,
        )

        try:
            mumble_snapshot = snapshot_mumble_live()
        except Exception as e:
            mumble_snapshot = {
                "meta": {"source": "takctl.services.mumble_live"},
                "server": {"host": None, "port": None, "connected": False},
                "channels": [],
                "users": [],
                "error": f"snapshot failed: {type(e).__name__}: {e}",
            }

        voice = _build_voice_for_user(
            username=username,
            header_callsign=str(header.get("callsign") or username),
            devices=devices,
            mumble_snapshot=mumble_snapshot,
        )
        voice_summary = _build_voice_summary(voice)

        return {
            "header": header,
            "identity": identity,
            "marti": {"groups": list(u.groups), "client": marti_client},
            "policy": {"id": policy_id},
            "authority": _build_authority(ident=ident),
            "lifecycle": lifecycle,
            "onboarding": _build_onboarding_out(rec),
            "activity": activity,
            "devices": devices,
            "selection": sel,
            "voice": voice,
            "voice_summary": voice_summary,
        }
