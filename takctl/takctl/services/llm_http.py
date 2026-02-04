from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional


def http_get_json(
    url: str,
    timeout_sec: float = 2.0,
) -> tuple[int, Optional[dict[str, Any]], Optional[str]]:
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


def http_post_json(
    url: str,
    payload: dict[str, Any],
    timeout_sec: float = 6.0,
) -> tuple[int, Optional[dict[str, Any]], Optional[str]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
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

