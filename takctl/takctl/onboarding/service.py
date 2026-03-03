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
        "unit": ctx.get("unit") or ctx.get("battalion"),
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
    """
    Keep this explicit; it matters for UI controls (editable/locked).
    """
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
    # best-effort: allow either boolean field or status enum
    if bool(getattr(rec, "offboarded", False)):
        return True
    st = _status_value(rec) or ""
    return st.lower() in ("offboarded", "retired", "disabled", "revoked")


def _artifact_evidence(*, username: str) -> Dict[str, Any]:
    """
    File-based evidence only. Never used as proof of client activity.
    """
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


def _db_query(db: Any, sql: str, params: tuple) -> list[dict[str, Any]]:
    """
    Support both:
      - takctl.services.db.client.DB (has .query/.query_one)
      - raw psycopg2 connection (has .cursor)
      - takctl.infra.db.DB-like (has .fetchall)
    """
    if db is None:
        return []
    if hasattr(db, "fetchall") and callable(getattr(db, "fetchall")):
        rows = db.fetchall(sql, params) or []
        return list(rows)
    if hasattr(db, "query") and callable(getattr(db, "query")):
        return list(db.query(sql, params))  # type: ignore
    cur = db.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    if rows and isinstance(rows[0], dict):
        return rows
    cols = [d[0] for d in (cur.description or [])]
    out = []
    for r in rows:
        out.append({cols[i]: r[i] for i in range(min(len(cols), len(r)))})
    return out


def _db_query_one(db: Any, sql: str, params: tuple) -> Optional[dict[str, Any]]:
    rows = _db_query(db, sql, params)
    return rows[0] if rows else None


def _fetch_marti_client_evidence(*, db: Any, username: str) -> Dict[str, Any]:
    """
    Evidence from TAK Server Postgres (Marti concepts), but kept SMALL:
      - public.client_endpoint (count + latest endpoint summary)
      - public.client_endpoint_event (latest event summary)
      - public.certificate (counts + latest cert summary)

    IMPORTANT:
      - DO NOT select client_endpoint_event.groups (bit varying / massive).
    """
    if db is None:
        return {"db_used": False}

    endpoints = _db_query(
        db,
        "SELECT id, callsign, uid, username FROM public.client_endpoint WHERE username=%s ORDER BY id DESC;",
        (username,),
    )
    endpoint_ids = [e.get("id") for e in endpoints if isinstance(e, dict) and e.get("id") is not None]
    endpoint_uids = [e.get("uid") for e in endpoints if isinstance(e, dict) and e.get("uid")]

    latest_endpoint: Optional[dict[str, Any]] = endpoints[0] if endpoints else None

    latest_event = None
    if endpoint_ids:
        latest_event = _db_query_one(
            db,
            """
            SELECT e.id, e.client_endpoint_id, e.connection_event_type_id, e.created_ts, e.client_version
            FROM public.client_endpoint_event e
            WHERE e.client_endpoint_id = ANY(%s)
            ORDER BY e.created_ts DESC
            LIMIT 1;
            """,
            (endpoint_ids,),
        )

    certs_user = _db_query(
        db,
        """
        SELECT id, issuance_date, effective_date, expiration_date, revocation_date, client_uid
        FROM public.certificate
        WHERE user_dn=%s
        ORDER BY issuance_date DESC;
        """,
        (username,),
    )
    certs_uid = []
    if endpoint_uids:
        certs_uid = _db_query(
            db,
            """
            SELECT id, issuance_date, effective_date, expiration_date, revocation_date, client_uid
            FROM public.certificate
            WHERE client_uid = ANY(%s)
            ORDER BY issuance_date DESC;
            """,
            (endpoint_uids,),
        )

    def _revoked_count(rows: list[dict[str, Any]]) -> int:
        n = 0
        for r in rows or []:
            if isinstance(r, dict) and r.get("revocation_date") is not None:
                n += 1
        return n

    latest_cert = (certs_user[0] if certs_user else (certs_uid[0] if certs_uid else None))

    out: Dict[str, Any] = {
        "db_used": True,
        "endpoints_n": len(endpoints),
        "endpoint_uids": endpoint_uids,
        "latest_endpoint": None,
        "latest_endpoint_event": None,
        "certs_by_user_dn_n": len(certs_user),
        "certs_by_client_uid_n": len(certs_uid),
        "certs_revoked_n": _revoked_count(certs_user) + _revoked_count(certs_uid),
        "latest_cert": None,
        # convenience flags for lifecycle
        "has_endpoint": bool(endpoints),
        "has_endpoint_event": bool(latest_event),
        "has_certificate": bool(certs_user or certs_uid),
    }

    if isinstance(latest_endpoint, dict):
        out["latest_endpoint"] = {
            "id": latest_endpoint.get("id"),
            "callsign": latest_endpoint.get("callsign"),
            "uid": latest_endpoint.get("uid"),
            "username": latest_endpoint.get("username"),
        }

    if isinstance(latest_event, dict):
        out["latest_endpoint_event"] = {
            "id": latest_event.get("id"),
            "client_endpoint_id": latest_event.get("client_endpoint_id"),
            "connection_event_type_id": latest_event.get("connection_event_type_id"),
            "created_ts": _iso_or_none(latest_event.get("created_ts")),
            "client_version": latest_event.get("client_version"),
        }

    if isinstance(latest_cert, dict):
        out["latest_cert"] = {
            "id": latest_cert.get("id"),
            "client_uid": latest_cert.get("client_uid"),
            "issuance_date": _iso_or_none(latest_cert.get("issuance_date")),
            "effective_date": _iso_or_none(latest_cert.get("effective_date")),
            "expiration_date": _iso_or_none(latest_cert.get("expiration_date")),
            "revocation_date": _iso_or_none(latest_cert.get("revocation_date")),
        }

    return out


def _build_onboarding_out(rec: Optional[OnboardingRecord]) -> Optional[Dict[str, Any]]:
    if rec is None:
        return None
    if hasattr(rec, "to_dict") and callable(getattr(rec, "to_dict")):
        return rec.to_dict()

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
        "callsign": getattr(act, "callsign", None),
        "last_cot_time": last_time_utc.isoformat() if last_time_utc else None,
        "stale": stale_utc.isoformat() if stale_utc else None,
        "is_current": bool(getattr(act, "is_current", False)),
        "age_sec": age_sec,
        "age_human": _age_human(age_sec) if isinstance(age_sec, int) else None,
        "recent_minutes": int(recent_minutes),
        "seen_recently": (age_sec is not None) and (age_sec <= (int(recent_minutes) * 60)),
    }


def _compute_lifecycle(
    *,
    username: str,
    ident: Optional[UserIdentity],
    selection: Any,
    rec: Optional[OnboardingRecord],
    activity: Optional[Dict[str, Any]],
    marti_client: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evidence-based lifecycle:
      SG0: external user (not created by TAKS)
      SG1: created by TAKS, but NO cert and NO endpoint and NO CoT
      SG2: certificate issued OR endpoint exists, but no events/CoT activity yet
      SG3: endpoint event exists OR CoT seen
      SG4: offboarded
    """
    evidence: Dict[str, Any] = {
        "username": username,
        "taks_identity_present": ident is not None,
        "taks_origin": getattr(ident, "origin", None) if ident is not None else None,
        "taks_password_known": bool(getattr(ident, "password_known", False) or getattr(ident, "password", None)) if ident is not None else False,
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
            label = "Active (endpoint events and/or CoT seen)"
        elif has_cert or has_endpoint:
            stage = "SG2"
            label = "Enrolled (certificate and/or endpoint present), not active yet"
        else:
            stage = "SG1"
            label = "Created by TAKS (no cert/endpoint/CoT yet)"

    return {"stage": stage, "label": label, "evidence": evidence}


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

            act = _build_activity_out(activity_map.get(r.username), recent_minutes=int(recent_minutes))
            marti_client = _fetch_marti_client_evidence(db=db, username=r.username) if db is not None else {"db_used": False}

            lifecycle = _compute_lifecycle(
                username=r.username,
                ident=ident,
                selection=None,
                rec=r.onboarding,
                activity=act,
                marti_client=marti_client,
            )

            user_out: Dict[str, Any] = {
                "header": header,
                "identity": identity,
                "marti": {"groups": list(r.groups), "client": marti_client},
                "policy": {"id": policy_id},
                "authority": _build_authority(ident=ident),
                "lifecycle": lifecycle,
                "onboarding_status": r.onboarding_status.value,
                "onboarding": _build_onboarding_out(r.onboarding),
                "activity": act,
                "selection": None,
            }

            users_out.append(user_out)

        total_users = len(users_out)
        cot_seen = sum(1 for u in users_out if u.get("activity") is not None)
        never_seen = total_users - cot_seen
        seen_recently = sum(1 for u in users_out if (u.get("activity") or {}).get("seen_recently") is True)
        is_current = sum(1 for u in users_out if (u.get("activity") or {}).get("is_current") is True)

        unknown_out: List[Dict[str, Any]] = []
        for e in unknown:
            out_e = dict(e)
            last_time = e.get("last_cot_time")
            stale = e.get("stale")
            if isinstance(last_time, datetime):
                out_e["last_cot_time"] = _to_utc(last_time).isoformat()
            if isinstance(stale, datetime):
                out_e["stale"] = _to_utc(stale).isoformat()
            unknown_out.append(out_e)

        unknown_seen_recently = sum(1 for e in unknown_out if e.get("seen_recently") is True)

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
        """
        from takctl.onboarding.selection import load_selection
        from takctl.onboarding.activity_pg import fetch_activity_for_usernames

        u = self.ud.get_user(username)
        if u is None:
            raise KeyError(username)

        rec = self.store.get_record(username)
        ident = self.store.get_identity(username)
        sel = load_selection(username) or None

        act_obj = None
        if db is not None:
            try:
                m = fetch_activity_for_usernames(db, [username])
                act_obj = m.get(username)
            except Exception:
                act_obj = None

        act = _build_activity_out(act_obj, recent_minutes=int(recent_minutes))
        marti_client = _fetch_marti_client_evidence(db=db, username=username) if db is not None else {"db_used": False}

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
            activity=act,
            marti_client=marti_client,
        )

        return {
            "header": header,
            "identity": identity,
            "marti": {"groups": list(u.groups), "client": marti_client},
            "policy": {"id": policy_id},
            "authority": _build_authority(ident=ident),
            "lifecycle": lifecycle,
            "onboarding": _build_onboarding_out(rec),
            "activity": act,
            "selection": sel,
        }
