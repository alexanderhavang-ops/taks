from __future__ import annotations

import time
from typing import Any


def _wait_for_cot_router_event(
    *,
    event_uid: str,
    timeout_seconds: float = 8.0,
    interval_seconds: float = 0.25,
) -> dict[str, Any]:
    from takctl.services.db.client import DB  # type: ignore

    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    attempts = 0
    sql = (
        "SELECT id, uid, cot_type, servertime "
        "FROM cot_router "
        "WHERE uid = %s "
        "ORDER BY servertime DESC "
        "LIMIT 1"
    )

    try:
        with DB() as db:
            while True:
                attempts += 1
                try:
                    row = db.query_one(sql, (event_uid,))
                except Exception as e:
                    return {
                        "ok": False,
                        "status": "probe_error",
                        "attempts": attempts,
                        "uid": event_uid,
                        "error": f"{type(e).__name__}: {e}",
                    }

                if row:
                    return {
                        "ok": True,
                        "status": "observed",
                        "attempts": attempts,
                        "id": row.get("id"),
                        "uid": row.get("uid"),
                        "cot_type": row.get("cot_type"),
                        "servertime": str(row.get("servertime") or ""),
                    }

                if time.monotonic() >= deadline:
                    break
                time.sleep(max(0.05, float(interval_seconds)))
    except Exception as e:
        return {
            "ok": False,
            "status": "probe_error",
            "attempts": attempts,
            "uid": event_uid,
            "error": f"{type(e).__name__}: {e}",
        }

    return {
        "ok": False,
        "status": "not_observed",
        "attempts": attempts,
        "uid": event_uid,
    }
