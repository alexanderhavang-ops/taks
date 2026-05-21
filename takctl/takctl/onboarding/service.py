from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from takctl.onboarding.models import OnboardingRecord, OnboardingStatus
from takctl.onboarding.store_filejson import FileJsonOnboardingStore, UserIdentity
from takctl.onboarding.user_directory import UserDirectory
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
    if v is not None and str(v).strip():
        return str(v)
    try:
        from takctl.onboarding.policy_registry import default_policy_id
        return default_policy_id()
    except Exception:
        return None


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
    # ident.identity is cached/derived display material and can become stale.
    # The configured callsign must be exactly one current value from ctx/user
    # edit state first, then policy-derived fallback, then legacy cached fallback.
    derived0 = ident.identity or {}
    derived = _derive_if_missing(policy_id=policy_id, ctx=ctx, derived={})

    return {
        "battalion": ctx.get("battalion"),
        "unit": ctx.get("unit") or ctx.get("battalion"),
        "company": ctx.get("company"),
        "platoon": ctx.get("platoon"),
        "squad": ctx.get("squad"),
        "role": ctx.get("role"),
        "battalion_role": ctx.get("battalion_role"),
        "callsign": derived0.get("callsign") or derived.get("callsign"),
        "team": ctx.get("team") or derived.get("team") or derived0.get("team"),
        "team_color": ctx.get("team_color") or derived.get("team_color") or derived0.get("team_color"),
        "atak_role_type": ctx.get("atak_role_type") or derived.get("atak_role_type") or derived0.get("atak_role_type"),
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


def _is_system_presence_row(row: Dict[str, Any]) -> bool:
    vals = [
        row.get("uid"),
        row.get("callsign"),
        row.get("username"),
        row.get("observed_callsign"),
        row.get("current_observed_callsign"),
    ]
    toks = {str(v or "").strip().lower() for v in vals if str(v or "").strip()}
    return (
        "android-martine" in toks
        or "martine" in toks
        or any(t.startswith("android-martine") for t in toks)
    )


def _observed_callsigns_from_devices(devices: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        v = str(value or "").strip()
        if not v:
            return
        key = v.upper()
        if key in seen:
            return
        seen.add(key)
        out.append(v)

    for d in devices or []:
        add((d or {}).get("current_observed_callsign"))
        add((d or {}).get("observed_callsign"))
        for key in ("observed_callsigns", "callsign_history", "previous_observed_callsigns"):
            vals = (d or {}).get(key)
            if isinstance(vals, list):
                for v in vals:
                    add(v)
        for ep in ((d or {}).get("endpoint_rows") or []):
            if isinstance(ep, dict):
                add(ep.get("callsign"))

    return out


def _build_callsigns_summary(*, configured_callsign: str, observed_callsigns: List[str]) -> Dict[str, Any]:
    cfg = str(configured_callsign or "").strip()
    obs = [str(x or "").strip() for x in (observed_callsigns or []) if str(x or "").strip()]
    current = obs[0] if obs else ""
    prev = [x for x in obs[1:] if str(x or "").strip().upper() != str(current or "").strip().upper()]

    cfg_key = cfg.upper()
    obs_keys = {x.upper() for x in obs}
    mismatch = bool(cfg and obs_keys and (cfg_key not in obs_keys or any(x != cfg_key for x in obs_keys)))

    return {
        "configured": cfg,
        "current_observed": current,
        "observed": obs,
        "previous_observed": prev,
        "observed_n": len(obs),
        "mismatch": mismatch,
    }


def _build_authority(*, ident: Optional[UserIdentity], backing_user_store: str = "userauthfile") -> Dict[str, Any]:
    origin = getattr(ident, "origin", None) if ident is not None else None
    password_known_flag = bool(getattr(ident, "password_known", False)) if ident is not None else False
    password_value_present = bool(getattr(ident, "password", None)) if ident is not None else False
    known_to_taks = bool(password_known_flag or password_value_present)
    overlay_present = ident is not None

    store = str(backing_user_store or "userauthfile").strip().lower()
    if store == "ldap":
        source = "ldap"
        notes = "Users and TAK groups are observed from the configured LDAP backend."
        writable = True
    else:
        source = "userauthfile"
        notes = "Users and TAK groups are observed from UserAuthenticationFile.xml."
        writable = True

    return {
        "tak_user": source,
        "groups": {
            "authoritative": source,
            "writable_by_taks": writable,
            "notes": notes,
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

    seen_sessions = set()
    channel_names: List[str] = []

    def add_channel(v: Any) -> None:
        s = str(v or "").strip()
        if s and s not in channel_names:
            channel_names.append(s)

    def add_match(m: Dict[str, Any]) -> None:
        if not bool((m or {}).get("connected_now")):
            return
        key = str((m or {}).get("session") or (m or {}).get("name") or (m or {}).get("callsign") or "").strip()
        if key:
            seen_sessions.add(key)
        add_channel((m or {}).get("channel_name"))

    for key in ("matches", "header_matches", "configured_matches", "username_matches"):
        for m in list(user.get(key) or []):
            if isinstance(m, dict):
                add_match(m)

    device_connected_now = 0
    seen_device_keys = set()
    for d in list((voice or {}).get("devices") or []):
        dv = dict((d or {}).get("voice") or {})
        if bool(dv.get("connected_now")):
            dk = str((d or {}).get("client_uid") or (d or {}).get("observed_callsign") or "").strip()
            if dk and dk not in seen_device_keys:
                seen_device_keys.add(dk)
                device_connected_now += 1
        for ch in list(dv.get("channel_names") or []):
            add_channel(ch)
        for m in list(dv.get("matches") or []):
            if isinstance(m, dict):
                add_match(m)

    return {
        "server": {
            "host": server.get("host"),
            "port": server.get("port"),
            "connected": bool(server.get("connected")),
        },
        "live_users": int(raw_counts.get("users") or 0),
        "matched_connected_users": int(len(seen_sessions)),
        "device_connected_now": int(device_connected_now),
        "connected_now": bool(seen_sessions or device_connected_now or user.get("connected_now")),
        "channel_names": sorted(channel_names),
    }



@dataclass(frozen=True)
class UserOnboardingView:
    username: str
    groups: List[str]
    onboarding_status: OnboardingStatus
    onboarding: Optional[OnboardingRecord]
    identity: Optional[UserIdentity]


class OnboardingService:
    def __init__(self, ud: UserDirectory, store: FileJsonOnboardingStore, backing_user_store: str = "userauthfile"):
        self.ud = ud
        self.store = store
        self.backing_user_store = str(backing_user_store or "userauthfile").strip().lower() or "userauthfile"

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
            unknown = [e for e in unknown if not _is_system_presence_row(e)]
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

            devices = list(devices_map.get(r.username, []) or [])
            observed_callsigns = _observed_callsigns_from_devices(devices)
            configured_callsign = str(identity.get("callsign") or header.get("callsign") or r.username).strip()
            header = dict(header)
            header["callsign"] = configured_callsign

            callsigns = _build_callsigns_summary(
                configured_callsign=configured_callsign,
                observed_callsigns=observed_callsigns,
            )
            header["configured_callsign"] = callsigns.get("configured")
            header["current_observed_callsign"] = callsigns.get("current_observed")
            header["observed_callsigns"] = ([callsigns.get("current_observed")] if callsigns.get("current_observed") else [])
            header["previous_observed_callsigns"] = list(callsigns.get("previous_observed") or [])
            header["all_observed_callsigns"] = list(callsigns.get("observed") or [])
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
                    "configured_callsign": configured_callsign,
                    "observed_callsigns": observed_callsigns,
                    "callsigns": _build_callsigns_summary(
                        configured_callsign=configured_callsign,
                        observed_callsigns=observed_callsigns,
                    ),
                    "identity": identity,
                    "marti": {"groups": list(r.groups), "client": marti_client},
                    "policy": {"id": policy_id},
                    "authority": _build_authority(ident=ident, backing_user_store=self.backing_user_store),
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
        observed_callsigns = _observed_callsigns_from_devices(devices)
        configured_callsign = str(identity.get("callsign") or header.get("callsign") or username).strip()
        header = dict(header)
        header["callsign"] = configured_callsign
        header["configured_callsign"] = configured_callsign
        observed_callsigns = _observed_callsigns_from_devices(devices)
        callsigns = _build_callsigns_summary(
            configured_callsign=str(header.get("callsign") or username),
            observed_callsigns=observed_callsigns,
        )
        header["configured_callsign"] = callsigns.get("configured")

        header["current_observed_callsign"] = callsigns.get("current_observed")
        header["observed_callsigns"] = ([callsigns.get("current_observed")] if callsigns.get("current_observed") else [])
        header["previous_observed_callsigns"] = list(callsigns.get("previous_observed") or [])
        header["all_observed_callsigns"] = list(callsigns.get("observed") or [])

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
            "configured_callsign": configured_callsign,
            "observed_callsigns": observed_callsigns,
            "callsigns": _build_callsigns_summary(
                configured_callsign=configured_callsign,
                observed_callsigns=observed_callsigns,
            ),
            "identity": identity,
            "marti": {"groups": list(u.groups), "client": marti_client},
            "policy": {"id": policy_id},
            "authority": _build_authority(ident=ident, backing_user_store=self.backing_user_store),
            "lifecycle": lifecycle,
            "onboarding_status": _status_value(rec) or OnboardingStatus.NEW.value,
            "onboarding": _build_onboarding_out(rec),
            "activity": activity,
            "devices": devices,
            "selection": sel,
            "voice": voice,
            "voice_summary": voice_summary,
        }
