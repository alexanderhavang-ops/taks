from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence


class OnboardingStatus(str, Enum):
    NEW = "new"
    PACKAGE_PENDING = "package_pending"
    PACKAGE_GENERATED = "package_generated"
    DOWNLOADED = "downloaded"
    # future:
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class UserRecord:
    """
    Observed identity record (external truth).
    """
    username: str
    groups: Sequence[str]


@dataclass(frozen=True)
class PackageMeta:
    """
    takctl-owned metadata about a generated onboarding package.
    """
    package_type: str                # e.g. "atak", "itak", "wintak"
    version: str                     # bundle version (e.g. "2026.02")
    generated_at: datetime
    plugins: Sequence[str]
    maps: Sequence[str]
    config_hash: str                 # e.g. sha256 of normalized config inputs


@dataclass(frozen=True)
class DeliveryMeta:
    """
    takctl-owned delivery tracking.
    """
    qr_generated: bool = False
    download_url: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    delivery_method: Optional[str] = None  # "qr" | "manual" | "auto-enroll"


@dataclass(frozen=True)
class OnboardingRecord:
    """
    takctl-owned onboarding state for a user (keyed by username).
    """
    username: str
    status: OnboardingStatus
    package: Optional[PackageMeta] = None
    delivery: Optional[DeliveryMeta] = None
# -----------------------------------------------------------------------------
# JSON helpers (used by API/status + card views)
# -----------------------------------------------------------------------------

from datetime import timezone as _timezone

def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_timezone.utc)
    dt = dt.astimezone(_timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _seq(x: Optional[Sequence[str]]) -> list[str]:
    return list(x or [])


def _opt_dt(dt: Optional[datetime]) -> Optional[str]:
    return _dt_to_iso(dt) if dt else None


# Add small serializers to the dataclasses. These are intentionally shallow and stable.

def _package_to_dict(p: PackageMeta) -> dict:
    return {
        "package_type": p.package_type,
        "version": p.version,
        "generated_at": _dt_to_iso(p.generated_at),
        "plugins": _seq(p.plugins),
        "maps": _seq(p.maps),
        "config_hash": p.config_hash,
    }


def _delivery_to_dict(d: DeliveryMeta) -> dict:
    return {
        "qr_generated": bool(d.qr_generated),
        "download_url": d.download_url,
        "downloaded_at": _opt_dt(d.downloaded_at),
        "delivery_method": d.delivery_method,
    }


def _onboarding_to_dict(r: OnboardingRecord) -> dict:
    return {
        "username": r.username,
        "status": r.status.value,
        "package": _package_to_dict(r.package) if r.package else None,
        "delivery": _delivery_to_dict(r.delivery) if r.delivery else None,
    }


# Monkey-patch style: attach methods without changing dataclass declarations.
# This keeps the patch small and avoids restructuring class bodies.

def _OnboardingRecord_to_dict(self) -> dict:  # type: ignore
    return _onboarding_to_dict(self)

OnboardingRecord.to_dict = _OnboardingRecord_to_dict  # type: ignore

