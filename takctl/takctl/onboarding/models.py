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

