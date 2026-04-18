from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/api/server-health", tags=["server-health"])

NODE_HEALTH_JSON = Path("/opt/tak/takctl-state/node-health.json")


def _summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rollup = payload.get("rollup") if isinstance(payload.get("rollup"), dict) else {}
    return {
        "overall": str(
            rollup.get("overall")
            or rollup.get("status")
            or payload.get("status")
            or "unknown"
        ),
        "generated_at": str(
            payload.get("generated_at")
            or payload.get("updated_at")
            or payload.get("checked_at")
            or payload.get("created_at")
            or ""
        ),
        "total": int(
            rollup.get("total")
            if isinstance(rollup.get("total"), int)
            else (len(payload.get("checks")) if isinstance(payload.get("checks"), list) else 0)
        ),
        "ok": int(rollup.get("ok") or 0),
        "warn": int(rollup.get("warn") or 0),
        "fail": int(rollup.get("fail") or 0),
        "skip": int(rollup.get("skip") or 0),
    }


def _read_payload() -> dict[str, Any]:
    raw = NODE_HEALTH_JSON.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict):
        return data
    return {"value": data}


@router.get("")
@router.get("/")
def server_health() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False,
        "exists": NODE_HEALTH_JSON.exists(),
        "path": str(NODE_HEALTH_JSON),
        "payload": {},
    }

    if not NODE_HEALTH_JSON.exists():
        out["error"] = "node-health.json missing"
        return out

    try:
        payload = _read_payload()
    except Exception as e:
        out["error"] = f"invalid node-health.json: {type(e).__name__}: {e}"
        return out

    out["ok"] = True
    out["payload"] = payload
    out["summary"] = _summary_from_payload(payload)
    out["generated_at"] = str(out["summary"].get("generated_at") or "")
    return out
