from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Client:
    callsign: str
    uid: str
    last_seen: datetime


@dataclass(frozen=True)
class Certificate:
    id: int
    client_uid: str
    subject_dn: str
    expires: datetime
    revoked_in_db: bool
    serial_hex: str | None = None
    revoked_in_crl: bool | None = None  # None if we couldn't determine


@dataclass(frozen=True)
class CRLStatus:
    path: str
    mtime_utc: datetime | None
    revoked_serials: set[str]

