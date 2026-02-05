from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from takctl.appctx import AppContext
# NOTE: Optional import. LLM subsystem must not fail to load if render.plan moved/changed.
try:
    from takctl.render.plan import RenderPlan  # type: ignore
except Exception:
    RenderPlan = object  # type: ignore
# NOTE: Optional import. LLM subsystem must not fail to load if heuristic renderer moved/changed.
try:
    from takctl.render.tactical_json import build_tactical_plan  # type: ignore
except Exception:
    build_tactical_plan = None  # type: ignore

from takctl.services.llm_http import http_get_json, http_post_json
from takctl.services.llm_systemd import systemd_show


def _env(name: str, default: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v or default


def llm_status(_ctx: AppContext | None) -> dict[str, Any]:
    base = _env("TAKS_LLM_URL", "http://127.0.0.1:8090").rstrip("/")
    unit = _env("TAKS_LLM_SYSTEMD_UNIT", "llm-local.service")

    payload_present = Path("/opt/llm").exists()
    sd = systemd_show(unit)

    active = (sd.get("ActiveState") or "").lower()
    sub = (sd.get("SubState") or "").lower()

    should_probe = payload_present or active == "active" or sub == "running"

    code = 0
    body = None
    err = None

    if should_probe:
        code, body, err = http_get_json(f"{base}/health", timeout_sec=2.0)

    ok = bool(code == 200 and isinstance(body, dict) and body.get("status") == "ok")

    return {
        "url": base,
        "unit": unit.replace(".service", ""),
        "local_payload_present": payload_present,
        "systemd": {
            "active": sd.get("ActiveState"),
            "sub": sd.get("SubState"),
            "load": sd.get("LoadState"),
            "unit_file_state": sd.get("UnitFileState"),
            "result": sd.get("Result"),
            "description": sd.get("Description"),
            "error": sd.get("error"),
        },
        "health": {
            "ok": ok,
            "status_code": code or None if should_probe else None,
            "body": body,
            "error": err if should_probe else None,
            "probed": should_probe,
        },
    }


def llm_plan(ctx: AppContext, data: dict[str, Any], title: str = "LLM Plan") -> RenderPlan:
    
    # Lazy-load heuristic planner if needed (optional dependency)
    global build_tactical_plan
    if build_tactical_plan is None:
        try:
            from takctl.render.tactical_json import build_tactical_plan as _btp  # type: ignore
            build_tactical_plan = _btp  # type: ignore
        except Exception:
            build_tactical_plan = None  # type: ignore

s = llm_status(ctx)
    base = s["url"]
    reachable = bool(s.get("health", {}).get("ok"))

    if reachable:
        code, body, err = http_post_json(
            f"{base}/plan",
            payload={"title": title, "data": data},
            timeout_sec=8.0,
        )

        if (
            code == 200
            and isinstance(body, dict)
            and "blocks" in body
            and "datasets" in body
        ):
            rp = RenderPlan.from_dict(body)
            rp.meta = dict(rp.meta or {})
            rp.meta["mode"] = "llm"
            return rp

        rp = build_tactical_plan(data, title=title)
        rp.meta = dict(rp.meta or {})
        rp.meta["mode"] = "heuristic"
        rp.meta["fallback_reason"] = (
            f"llm_plan_failed: http={code or 'n/a'} err={err or 'n/a'}"
        )
        return rp

    rp = build_tactical_plan(data, title=title)
    rp.meta = dict(rp.meta or {})
    rp.meta["mode"] = "heuristic"
    rp.meta["fallback_reason"] = "llm_unreachable"
    return rp

