from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .models import DeliveryMeta, OnboardingRecord, OnboardingStatus, PackageMeta
from .store import OnboardingStore


def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_to_dt(s: str) -> datetime:
    s = (s or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# -----------------------------------------------------------------------------
# New lightweight persisted objects (kept boring JSON)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class UserIdentity:
    """
    Persisted TAKS "authoritative" user identity record.

    - origin="taks": TAKS created the Marti user → password is known here.
    - origin="marti": user exists in Marti but created externally → password is unknown here.
    """
    username: str
    origin: str  # "taks" | "marti"
    ctx: Dict[str, Any]  # policy inputs: unit/company/platoon/n/role/etc
    identity: Dict[str, Any]  # outputs: callsign/team/atak_role_type
    password_known: bool
    password: Optional[str]  # NOTE: plaintext for now (later: encrypt)
    created_at_utc: datetime
    updated_at_utc: datetime

    def to_json(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "origin": self.origin,
            "ctx": self.ctx or {},
            "identity": self.identity or {},
            "password": {
                "known": bool(self.password_known),
                "value": self.password if self.password_known else None,
            },
            "created_at_utc": _dt_to_iso(self.created_at_utc),
            "updated_at_utc": _dt_to_iso(self.updated_at_utc),
        }

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "UserIdentity":
        pw = d.get("password") or {}
        known = bool(pw.get("known", False))
        val = pw.get("value") if known else None
        return UserIdentity(
            username=d.get("username") or "",
            origin=(d.get("origin") or "marti").strip().lower(),
            ctx=d.get("ctx") or {},
            identity=d.get("identity") or {},
            password_known=known,
            password=val,
            created_at_utc=_iso_to_dt(d.get("created_at_utc") or ""),
            updated_at_utc=_iso_to_dt(d.get("updated_at_utc") or ""),
        )


@dataclass(frozen=True)
class CardToken:
    token: str
    username: str
    expires_at_utc: datetime
    reveal_password: bool
    created_at_utc: datetime

    def to_json(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "username": self.username,
            "expires_at_utc": _dt_to_iso(self.expires_at_utc),
            "reveal_password": bool(self.reveal_password),
            "created_at_utc": _dt_to_iso(self.created_at_utc),
        }

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "CardToken":
        return CardToken(
            token=d.get("token") or "",
            username=d.get("username") or "",
            expires_at_utc=_iso_to_dt(d.get("expires_at_utc") or ""),
            reveal_password=bool(d.get("reveal_password", False)),
            created_at_utc=_iso_to_dt(d.get("created_at_utc") or ""),
        )

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now >= self.expires_at_utc


class FileJsonOnboardingStore(OnboardingStore):
    """
    Simple file-backed store:

      root/
        users/<username>.json         (existing: OnboardingRecord)
        identities/<username>.json    (new: UserIdentity)
        cards/<token>.json            (new: CardToken)
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)

        self.users_dir = self.root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

        self.identities_dir = self.root / "identities"
        self.identities_dir.mkdir(parents=True, exist_ok=True)

        self.cards_dir = self.root / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Existing OnboardingRecord storage (backward compatible)
    # -------------------------------------------------------------------------

    def list_records(self) -> Sequence[OnboardingRecord]:
        out = []
        for p in sorted(self.users_dir.glob("*.json")):
            out.append(self._load_onboarding_file(p))
        return out

    def get_record(self, username: str) -> Optional[OnboardingRecord]:
        p = self.users_dir / f"{username}.json"
        if not p.exists():
            return None
        return self._load_onboarding_file(p)

    def upsert_record(self, record: OnboardingRecord) -> None:
        p = self.users_dir / f"{record.username}.json"
        tmp = p.with_suffix(".json.tmp")
        data = self._onboarding_to_json(record)
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

    def _onboarding_to_json(self, r: OnboardingRecord) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "username": r.username,
            "status": r.status.value,
            "package": None,
            "delivery": None,
        }
        if r.package:
            d["package"] = {
                "package_type": r.package.package_type,
                "version": r.package.version,
                "generated_at": _dt_to_iso(r.package.generated_at),
                "plugins": list(r.package.plugins),
                "maps": list(r.package.maps),
                "config_hash": r.package.config_hash,
            }
        if r.delivery:
            d["delivery"] = {
                "qr_generated": r.delivery.qr_generated,
                "download_url": r.delivery.download_url,
                "downloaded_at": _dt_to_iso(r.delivery.downloaded_at) if r.delivery.downloaded_at else None,
                "delivery_method": r.delivery.delivery_method,
            }
        return d

    def _load_onboarding_file(self, p: Path) -> OnboardingRecord:
        raw = json.loads(p.read_text(encoding="utf-8"))

        pkg = None
        if raw.get("package"):
            pr = raw["package"]
            pkg = PackageMeta(
                package_type=pr["package_type"],
                version=pr["version"],
                generated_at=_iso_to_dt(pr["generated_at"]),
                plugins=pr.get("plugins", []),
                maps=pr.get("maps", []),
                config_hash=pr["config_hash"],
            )

        dlv = None
        if raw.get("delivery"):
            dr = raw["delivery"]
            dlv = DeliveryMeta(
                qr_generated=bool(dr.get("qr_generated", False)),
                download_url=dr.get("download_url"),
                downloaded_at=_iso_to_dt(dr["downloaded_at"]) if dr.get("downloaded_at") else None,
                delivery_method=dr.get("delivery_method"),
            )

        return OnboardingRecord(
            username=raw["username"],
            status=OnboardingStatus(raw["status"]),
            package=pkg,
            delivery=dlv,
        )

    # -------------------------------------------------------------------------
    # New: UserIdentity storage
    # -------------------------------------------------------------------------

    def get_identity(self, username: str) -> Optional[UserIdentity]:
        u = (username or "").strip()
        if not u:
            return None
        p = self.identities_dir / f"{u}.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        try:
            return UserIdentity.from_json(raw)
        except Exception:
            return None

    def upsert_identity(
        self,
        *,
        username: str,
        origin: str,
        ctx: Dict[str, Any],
        identity: Dict[str, Any],
        password: Optional[str],
    ) -> UserIdentity:
        u = (username or "").strip()
        if not u:
            raise ValueError("username required")

        now = datetime.now(timezone.utc)

        existing = self.get_identity(u)
        created_at = existing.created_at_utc if existing else now

        password_known = bool(password) and (origin.strip().lower() == "taks")

        rec = UserIdentity(
            username=u,
            origin=(origin or "marti").strip().lower(),
            ctx=ctx or {},
            identity=identity or {},
            password_known=password_known,
            password=password if password_known else None,
            created_at_utc=created_at,
            updated_at_utc=now,
        )

        p = self.identities_dir / f"{u}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

        return rec

    # -------------------------------------------------------------------------
    # New: CardToken storage (random URI + TTL)
    # -------------------------------------------------------------------------

    def issue_card_token(
        self,
        *,
        username: str,
        ttl_hours: int = 24,
        reveal_password: bool = False,
    ) -> CardToken:
        u = (username or "").strip()
        if not u:
            raise ValueError("username required")

        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)  # unguessable, URL safe
        expires = now + timedelta(hours=int(ttl_hours))

        ct = CardToken(
            token=token,
            username=u,
            expires_at_utc=expires,
            reveal_password=bool(reveal_password),
            created_at_utc=now,
        )

        p = self.cards_dir / f"{token}.json"
        p.write_text(json.dumps(ct.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ct


    def create_card_token(self, *, username: str, ttl_sec: int, reveal_password: bool) -> "CardToken":
        """Compat wrapper expected by API. Delegates to issue_card_token().
        ttl_sec is converted to ttl_hours (ceil), minimum 1 hour.
        """
        ttl_sec = int(ttl_sec)
        ttl_hours = max(1, (ttl_sec + 3599) // 3600)
        return self.issue_card_token(username=username, ttl_hours=ttl_hours, reveal_password=bool(reveal_password))

    def upsert_card_token(self, *, username: str, ttl_sec: int, reveal_password: bool) -> "CardToken":
        """Compat alias (some callers may look for upsert_card_token)."""
        return self.create_card_token(username=username, ttl_sec=ttl_sec, reveal_password=reveal_password)
    def get_card_token(self, token: str) -> Optional[CardToken]:
        t = (token or "").strip()
        if not t:
            return None
        p = self.cards_dir / f"{t}.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        try:
            return CardToken.from_json(raw)
        except Exception:
            return None
