from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Sequence


def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _opt_dt(dt: Optional[datetime]) -> Optional[str]:
    return _dt_to_iso(dt) if dt else None


def _seq(x: Optional[Sequence[str]]) -> list[str]:
    return list(x or [])


class OnboardingStatus(str, Enum):
    NEW = "new"
    PACKAGE_PENDING = "package_pending"
    PACKAGE_GENERATED = "package_generated"
    DOWNLOADED = "downloaded"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True)
class UserRecord:
    username: str
    groups: Sequence[str]


@dataclass(frozen=True)
class PackageMeta:
    package_type: str
    version: str
    generated_at: datetime
    plugins: Sequence[str]
    maps: Sequence[str]
    config_hash: str

    def to_dict(self) -> dict:
        return {
            "package_type": self.package_type,
            "version": self.version,
            "generated_at": _dt_to_iso(self.generated_at),
            "plugins": _seq(self.plugins),
            "maps": _seq(self.maps),
            "config_hash": self.config_hash,
        }


@dataclass(frozen=True)
class DeliveryMeta:
    qr_generated: bool = False
    download_url: Optional[str] = None
    downloaded_at: Optional[datetime] = None
    delivery_method: Optional[str] = None  # "qr" | "manual" | "auto-enroll"

    def to_dict(self) -> dict:
        return {
            "qr_generated": bool(self.qr_generated),
            "download_url": self.download_url,
            "downloaded_at": _opt_dt(self.downloaded_at),
            "delivery_method": self.delivery_method,
        }


@dataclass(frozen=True)
class DeviceRecord:
    client_uid: str
    client_type: Optional[str] = None      # atak | itak | wintak | vx | other
    version: Optional[str] = None

    cot_uid: Optional[str] = None
    cot_callsign: Optional[str] = None
    last_cot_time: Optional[datetime] = None
    stale: Optional[datetime] = None
    is_current: Optional[bool] = None

    welcome_sent_at: Optional[datetime] = None
    voice_offer_sent_at: Optional[datetime] = None
    voice_requested_at: Optional[datetime] = None
    voice_mission_sent_at: Optional[datetime] = None
    voice_connected_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "client_uid": self.client_uid,
            "client_type": self.client_type,
            "version": self.version,
            "cot_uid": self.cot_uid,
            "cot_callsign": self.cot_callsign,
            "last_cot_time": _opt_dt(self.last_cot_time),
            "stale": _opt_dt(self.stale),
            "is_current": self.is_current,
            "welcome_sent_at": _opt_dt(self.welcome_sent_at),
            "voice_offer_sent_at": _opt_dt(self.voice_offer_sent_at),
            "voice_requested_at": _opt_dt(self.voice_requested_at),
            "voice_mission_sent_at": _opt_dt(self.voice_mission_sent_at),
            "voice_connected_at": _opt_dt(self.voice_connected_at),
        }


@dataclass(frozen=True)
class OnboardingRecord:
    username: str
    status: OnboardingStatus
    package: Optional[PackageMeta] = None
    delivery: Optional[DeliveryMeta] = None
    devices: Sequence[DeviceRecord] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "status": self.status.value,
            "package": self.package.to_dict() if self.package else None,
            "delivery": self.delivery.to_dict() if self.delivery else None,
            "devices": [d.to_dict() for d in (self.devices or ())],
        }
