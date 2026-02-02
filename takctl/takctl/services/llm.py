from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional

from takctl.appctx import AppContext


def _http_get_json(url: str, timeout_sec: float = 2.0) -> tuple[int, Optional[dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as r:
            code = int(getattr(r, "status", 200))
            raw = r.read().decode("utf-8", "replace").strip()
            if not raw:
                return code, None, None
            try:
                return code, json.loads(raw), None
            except Exception:
                return code, None, f"Non-JSON response: {raw[:200]}"
    except Exception as e:
        return 0, None, str(e)


def llm_status(_ctx: AppContext) -> dict[str, Any]:
    # minimal v1: fixed local URL
    base = "http://127.0.0.1:8090"
    code, body, err = _http_get_json(f"{base}/health", timeout_sec=2.0)
    ok = (code == 200 and isinstance(body, dict) and body.get("status") == "ok")
    return {
        "url": base,
        "health": {
            "ok": bool(ok),
            "http": (code or None),
            "body": body,
            "error": err,
        },
    }
