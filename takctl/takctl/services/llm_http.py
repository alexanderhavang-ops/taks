from __future__ import annotations

import binascii
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple


def _http_dump_dir() -> str:
    return (os.environ.get("TAKS_LLM_HTTP_DUMP_DIR") or "").strip()


def _http_dump_enabled() -> bool:
    return bool(_http_dump_dir())


def _http_dump(tag: str, data: bytes) -> Optional[str]:
    d = _http_dump_dir()
    if not d:
        return None
    out = Path(d)
    out.mkdir(parents=True, exist_ok=True)
    fn = out / f"{tag}.{int(time.time() * 1000)}.bin"
    fn.write_bytes(data)
    return str(fn)


def _hex_head_tail(data: bytes, n: int = 64) -> dict[str, Any]:
    h = binascii.hexlify(data[:n]).decode("ascii")
    t = binascii.hexlify(data[-n:]).decode("ascii") if len(data) >= n else binascii.hexlify(data).decode("ascii")
    return {"bytes": len(data), "head_hex": h, "tail_hex": t}


def http_get_json(
    url: str,
    *,
    timeout_sec: float = 30.0,
    headers: Optional[dict[str, str]] = None,
) -> Tuple[int, Any, Optional[str]]:
    """
    JSON GET with urllib.
    Returns: (status_code, parsed_json_or_text, err)
    """
    h = {"accept": "application/json"}
    if headers:
        h.update(headers)

    req = urllib.request.Request(url, headers=h, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)

            if _http_dump_enabled():
                meta = {
                    "method": "GET",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "raw": _hex_head_tail(raw),
                }
                _http_dump("llm_http.get.response.meta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"))
                _http_dump("llm_http.get.response.body", raw)

            txt = raw.decode("utf-8", "replace")
            try:
                return status, json.loads(txt), None
            except Exception:
                return status, txt, "json_decode_failed"
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"


def http_post_json(
    url: str,
    payload: Any,
    *,
    timeout_sec: float = 60.0,
    headers: Optional[dict[str, str]] = None,
) -> Tuple[int, Any, Optional[str]]:
    """
    JSON POST with urllib.
    Returns: (status_code, parsed_json_or_text, err)

    If TAKS_LLM_HTTP_DUMP_DIR is set, dumps request/response bytes + meta.
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8", "ignore")

    h = {"content-type": "application/json", "accept": "application/json"}
    if headers:
        h.update(headers)

    if _http_dump_enabled():
        meta = {"method": "POST", "url": url, "body": _hex_head_tail(data), "headers": h}
        _http_dump("llm_http.post.request.meta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"))
        _http_dump("llm_http.post.request.body", data)

    req = urllib.request.Request(url, data=data, headers=h, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)

            if _http_dump_enabled():
                meta = {
                    "method": "POST",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "raw": _hex_head_tail(raw),
                }
                _http_dump("llm_http.post.response.meta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"))
                _http_dump("llm_http.post.response.body", raw)

            txt = raw.decode("utf-8", "replace")
            try:
                return status, json.loads(txt), None
            except Exception:
                return status, txt, "json_decode_failed"

    except urllib.error.HTTPError as e:
        # HTTPError is file-like; it can have a JSON body too.
        try:
            raw = e.read() or b""
        except Exception:
            raw = b""

        status = int(getattr(e, "code", 0) or 0)
        reason = getattr(e, "reason", None)

        if _http_dump_enabled():
            meta = {
                "method": "POST",
                "url": url,
                "status": status,
                "reason": reason,
                "headers": dict(getattr(e, "headers", {}) or {}),
                "raw": _hex_head_tail(raw),
            }
            _http_dump("llm_http.post.error.meta", (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"))
            _http_dump("llm_http.post.error.body", raw)

        txt = raw.decode("utf-8", "replace")
        try:
            body: Any = json.loads(txt)
        except Exception:
            body = txt
        return status, body, f"HTTPError: {status} {reason}"

    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"
