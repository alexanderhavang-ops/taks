from __future__ import annotations

import re

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_pg_timestamptz(s: str) -> datetime:
    """
    Parse Postgres timestamptz strings coming from psql -At that look like:
      2026-01-30 08:12:30.716-05
    which is NOT ISO-8601 because the offset is missing minutes.

    We normalize to:
      2026-01-30T08:12:30.716-05:00
    """
    s = s.strip()
    s = s.replace(" ", "T", 1)

    # If tz offset is just hours (+02 / -05), append :00
    if re.search(r"[+-]\d{2}$", s):
        s = s + ":00"

    return datetime.fromisoformat(s)
