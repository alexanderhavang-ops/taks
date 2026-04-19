from __future__ import annotations

import json
import uuid
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
    s = str(s or "").strip()
    if not s:
        return datetime.now(timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class UserIdentity:
    username: str
    origin: str  # "taks" | "marti"
    ctx: Dict[str, Any]
    identity: Dict[str, Any]
    password_known: bool
    password: Optional[str]
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
        value = pw.get("value") if known else None
        return UserIdentity(
            username=str(d.get("username") or "").strip(),
            origin=str(d.get("origin") or "marti").strip().lower(),
            ctx=dict(d.get("ctx") or {}),
            identity=dict(d.get("identity") or {}),
            password_known=known,
            password=value,
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
            token=str(d.get("token") or "").strip(),
            username=str(d.get("username") or "").strip(),
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
    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)

        self.users_dir = self.root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

        self.identities_dir = self.root / "identities"
        self.identities_dir.mkdir(parents=True, exist_ok=True)

        self.cards_dir = self.root / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # OnboardingRecord
    # ------------------------------------------------------------------

    def list_records(self) -> Sequence[OnboardingRecord]:
        out = []
        for p in sorted(self.users_dir.glob("*.json")):
            out.append(self._load_onboarding_file(p))
        return out

    def get_record(self, username: str) -> Optional[OnboardingRecord]:
        u = str(username or "").strip()
        if not u:
            return None
        p = self.users_dir / f"{u}.json"
        if not p.exists():
            return None
        return self._load_onboarding_file(p)

    def upsert_record(self, record: OnboardingRecord) -> None:
        p = self.users_dir / f"{record.username}.json"
        tmp = p.with_name(f"{p.name}.tmp.{uuid.uuid4().hex}")
        tmp.write_text(json.dumps(self._onboarding_to_json(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

    def _onboarding_to_json(self, r: OnboardingRecord) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "username": r.username,
            "status": r.status.value,
            "package": None,
            "delivery": None,
        }

        if r.package is not None:
            out["package"] = {
                "package_type": r.package.package_type,
                "version": r.package.version,
                "generated_at": _dt_to_iso(r.package.generated_at),
                "plugins": list(r.package.plugins),
                "maps": list(r.package.maps),
                "config_hash": r.package.config_hash,
            }

        if r.delivery is not None:
            out["delivery"] = {
                "qr_generated": bool(r.delivery.qr_generated),
                "download_url": r.delivery.download_url,
                "downloaded_at": _dt_to_iso(r.delivery.downloaded_at) if r.delivery.downloaded_at else None,
                "delivery_method": r.delivery.delivery_method,
            }

        return out

    def _load_onboarding_file(self, p: Path) -> OnboardingRecord:
        raw = json.loads(p.read_text(encoding="utf-8"))

        pkg = None
        pkg_raw = raw.get("package")
        if pkg_raw:
            pkg = PackageMeta(
                package_type=str(pkg_raw["package_type"]),
                version=str(pkg_raw["version"]),
                generated_at=_iso_to_dt(pkg_raw["generated_at"]),
                plugins=list(pkg_raw.get("plugins") or []),
                maps=list(pkg_raw.get("maps") or []),
                config_hash=str(pkg_raw["config_hash"]),
            )

        dlv = None
        dlv_raw = raw.get("delivery")
        if dlv_raw:
            dlv = DeliveryMeta(
                qr_generated=bool(dlv_raw.get("qr_generated", False)),
                download_url=dlv_raw.get("download_url"),
                downloaded_at=_iso_to_dt(dlv_raw["downloaded_at"]) if dlv_raw.get("downloaded_at") else None,
                delivery_method=dlv_raw.get("delivery_method"),
            )

        return OnboardingRecord(
            username=str(raw["username"]),
            status=OnboardingStatus(str(raw["status"])),
            package=pkg,
            delivery=dlv,
        )

    # ------------------------------------------------------------------
    # UserIdentity
    # ------------------------------------------------------------------

    def get_identity(self, username: str) -> Optional[UserIdentity]:
        u = str(username or "").strip()
        if not u:
            return None
        p = self.identities_dir / f"{u}.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return UserIdentity.from_json(raw)

    def upsert_identity(
        self,
        *,
        username: str,
        origin: str,
        ctx: Dict[str, Any],
        identity: Dict[str, Any],
        password: Optional[str],
    ) -> UserIdentity:
        u = str(username or "").strip()
        if not u:
            raise ValueError("username required")

        now = datetime.now(timezone.utc)
        existing = self.get_identity(u)
        created_at = existing.created_at_utc if existing is not None else now

        normalized_origin = str(origin or "marti").strip().lower()
        password_known = bool(password) and normalized_origin == "taks"

        rec = UserIdentity(
            username=u,
            origin=normalized_origin,
            ctx=dict(ctx or {}),
            identity=dict(identity or {}),
            password_known=password_known,
            password=(password if password_known else None),
            created_at_utc=created_at,
            updated_at_utc=now,
        )

        p = self.identities_dir / f"{u}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)
        return rec

    # ------------------------------------------------------------------
    # CardToken
    # ------------------------------------------------------------------

    def create_card_token(
        self,
        *,
        username: str,
        ttl_sec: int,
        reveal_password: bool,
    ) -> CardToken:
        u = str(username or "").strip()
        if not u:
            raise ValueError("username required")

        ttl = int(ttl_sec)
        if ttl <= 0:
            raise ValueError("ttl_sec must be > 0")

        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(1, ttl))
        token = secrets.token_urlsafe(32)

        ct = CardToken(
            token=token,
            username=u,
            expires_at_utc=expires,
            reveal_password=bool(reveal_password),
            created_at_utc=now,
        )

        p = self.cards_dir / f"{token}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ct.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)
        return ct

    def upsert_card_token(
        self,
        *,
        username: str,
        ttl_sec: int,
        reveal_password: bool,
    ) -> CardToken:
        return self.create_card_token(
            username=username,
            ttl_sec=ttl_sec,
            reveal_password=reveal_password,
        )

    def get_card_token(self, token: str) -> Optional[CardToken]:
        t = str(token or "").strip()
        if not t:
            return None
        p = self.cards_dir / f"{t}.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        ct = CardToken.from_json(raw)
        if ct.is_expired():
            try:
                p.unlink()
            except Exception:
                pass
            return None
        return ct
