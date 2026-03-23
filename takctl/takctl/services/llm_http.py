from __future__ import annotations

import binascii
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

from takctl.config import load_config


ALEXANDER_RAW_LOG = Path("/tmp/alexander.txt")


def _alexander_append(tag: str, raw: bytes) -> None:
    """
    ALWAYS best-effort append the exact socket bytes (HTTP body) we received/sent.
    MUST NEVER raise (debug must not break production runs).
    """
    try:
        ts = int(time.time() * 1000)
        with open(ALEXANDER_RAW_LOG, "ab") as f:
            f.write(f"\n===== {tag} ts_ms={ts} =====\n".encode("utf-8", "ignore"))
            f.write(raw)
            if raw and (not raw.endswith(b"\n")):
                f.write(b"\n")
            f.write(b"===== END =====\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        return


def _alexander_append_json(tag: str, obj: Any) -> None:
    try:
        raw = (json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8", "ignore")
    except Exception as e:
        try:
            fallback = {
                "alexander_json_dump_failed": True,
                "tag": tag,
                "exc": f"{type(e).__name__}: {e}",
                "obj_type": type(obj).__name__,
                "obj_repr": repr(obj)[:4000],
            }
            raw = (json.dumps(fallback, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore")
        except Exception:
            raw = (f"alexander_json_dump_failed tag={tag} exc={type(e).__name__}: {e}\n").encode("utf-8", "ignore")

    _alexander_append(tag, raw)


def _http_dump_dir() -> str:
    """
    Debug dump dir from takctl.conf.
    Reuse llm_state_dir as base and keep dumps under http-dumps/.
    Empty string disables file dumps.
    """
    try:
        cfg = load_config()
        base = (cfg.llm_state_dir or "").strip()
        if not base:
            return ""
        return str(Path(base) / "http-dumps")
    except Exception:
        return ""


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


def _sha256_hex(data: bytes) -> str:
    try:
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


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

    _alexander_append_json(
        "llm_http.get.request.meta",
        {
            "method": "GET",
            "url": url,
            "timeout_sec": timeout_sec,
            "headers": h,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)

            _alexander_append_json(
                "llm_http.get.response.meta",
                {
                    "method": "GET",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "body_sha256": _sha256_hex(raw),
                    "raw": _hex_head_tail(raw),
                },
            )
            _alexander_append("llm_http.get.response.body", raw)

            if _http_dump_enabled():
                meta = {
                    "method": "GET",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "raw": _hex_head_tail(raw),
                }
                _http_dump(
                    "llm_http.get.response.meta",
                    (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"),
                )
                _http_dump("llm_http.get.response.body", raw)

            txt = raw.decode("utf-8", "replace")
            try:
                return status, json.loads(txt), None
            except Exception:
                return status, txt, "json_decode_failed"

    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b""
        except Exception:
            raw = b""
        status = int(getattr(e, "code", 0) or 0)

        _alexander_append_json(
            "llm_http.get.error.meta",
            {
                "method": "GET",
                "url": url,
                "timeout_sec": timeout_sec,
                "status": status,
                "err": f"{type(e).__name__}: {e}",
                "body_sha256": _sha256_hex(raw),
                "raw": _hex_head_tail(raw),
            },
        )
        if raw:
            _alexander_append("llm_http.get.error.body", raw)

        txt = raw.decode("utf-8", "replace")
        try:
            body = json.loads(txt) if txt else None
        except Exception:
            body = txt
        return status, body, f"{type(e).__name__}: {e}"

    except Exception as e:
        _alexander_append_json(
            "llm_http.get.error.meta",
            {
                "method": "GET",
                "url": url,
                "timeout_sec": timeout_sec,
                "err": f"{type(e).__name__}: {e}",
            },
        )
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

    If debug dump dir is enabled from takctl.conf, dumps request/response bytes + meta.
    Also ALWAYS appends request/response bytes + meta to /tmp/alexander.txt (best-effort).
    """
    try:
        if isinstance(payload, dict):
            t = payload.get("temperature")
            if (t == 0 or t == 0.0) and ("seed" not in payload):
                payload["seed"] = 0
    except Exception:
        pass

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8", "ignore")

    h = {"content-type": "application/json", "accept": "application/json"}
    if headers:
        h.update(headers)

    _alexander_append_json(
        "llm_http.post.request.meta",
        {
            "method": "POST",
            "url": url,
            "timeout_sec": timeout_sec,
            "headers": h,
            "body_sha256": _sha256_hex(data),
            "raw": _hex_head_tail(data),
        },
    )
    _alexander_append("llm_http.post.request.body", data)

    if _http_dump_enabled():
        meta = {"method": "POST", "url": url, "body": _hex_head_tail(data), "headers": h}
        _http_dump(
            "llm_http.post.request.meta",
            (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"),
        )
        _http_dump("llm_http.post.request.body", data)

    req = urllib.request.Request(url, data=data, headers=h, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)

            _alexander_append_json(
                "llm_http.post.response.meta",
                {
                    "method": "POST",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "body_sha256": _sha256_hex(raw),
                    "raw": _hex_head_tail(raw),
                },
            )
            _alexander_append("llm_http.post.response.body", raw)

            if _http_dump_enabled():
                meta = {
                    "method": "POST",
                    "url": url,
                    "status": status,
                    "reason": getattr(resp, "reason", None),
                    "headers": dict(resp.headers) if getattr(resp, "headers", None) else None,
                    "raw": _hex_head_tail(raw),
                }
                _http_dump(
                    "llm_http.post.response.meta",
                    (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"),
                )
                _http_dump("llm_http.post.response.body", raw)

            txt = raw.decode("utf-8", "replace")
            try:
                return status, json.loads(txt), None
            except Exception:
                return status, txt, "json_decode_failed"

    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b""
        except Exception:
            raw = b""
        status = int(getattr(e, "code", 0) or 0)

        _alexander_append_json(
            "llm_http.post.error.meta",
            {
                "method": "POST",
                "url": url,
                "timeout_sec": timeout_sec,
                "status": status,
                "err": f"{type(e).__name__}: {e}",
                "body_sha256": _sha256_hex(raw),
                "raw": _hex_head_tail(raw),
            },
        )
        if raw:
            _alexander_append("llm_http.post.error.body", raw)

        if _http_dump_enabled():
            meta = {
                "method": "POST",
                "url": url,
                "timeout_sec": timeout_sec,
                "status": status,
                "err": f"{type(e).__name__}: {e}",
                "raw": _hex_head_tail(raw),
            }
            _http_dump(
                "llm_http.post.error.meta",
                (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8", "ignore"),
            )
            if raw:
                _http_dump("llm_http.post.error.body", raw)

        txt = raw.decode("utf-8", "replace")
        try:
            body = json.loads(txt) if txt else None
        except Exception:
            body = txt
        return status, body, f"{type(e).__name__}: {e}"

    except Exception as e:
        _alexander_append_json(
            "llm_http.post.error.meta",
            {
                "method": "POST",
                "url": url,
                "timeout_sec": timeout_sec,
                "err": f"{type(e).__name__}: {e}",
            },
        )
        return 0, None, f"{type(e).__name__}: {e}"
