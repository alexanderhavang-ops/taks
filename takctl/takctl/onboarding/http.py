from __future__ import annotations

from urllib.parse import splitport

from fastapi import HTTPException, Request


def forwarded_host_only(req: Request) -> str:
    raw = (req.headers.get("x-forwarded-host") or req.headers.get("host") or "localhost").split(",")[0].strip()
    raw = raw.split("/")[0].strip()

    host, _port = splitport(raw)
    return (host or raw).strip()


def external_base(req: Request) -> str:
    """
    Proxy-aware external base URL.

    IMPORTANT: /takctl is dead. This returns proto://host with NO prefix.
    """
    h = req.headers
    proto = (h.get("x-forwarded-proto") or req.url.scheme or "https").split(",")[0].strip()
    host = (h.get("x-forwarded-host") or h.get("host") or req.url.hostname or "localhost").split(",")[0].strip()
    return f"{proto}://{host}"


def password_from_req(req: Request) -> str | None:
    """
    Experimental helper for Path C (enroll QR with creds).

    Prefer header (does not leak into URL/history):
      - x-taks-password: <password>

    Also supports query param for convenience:
      - ?password=...

    Returns None if not provided.
    """
    pw = (req.headers.get("x-taks-password") or "").strip()
    if pw:
        return pw
    pw = (req.query_params.get("password") or "").strip()
    if pw:
        return pw
    return None


def q(req: Request, key: str, default: str | None = None) -> str | None:
    v = req.query_params.get(key)
    if v is None:
        return default
    v = v.strip()
    return v if v else default


def bool_q(req: Request, key: str, default: bool = False) -> bool:
    v = (req.query_params.get(key) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def qi(req: Request, key: str) -> int | None:
    v = q(req, key, None)
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid int for {key}: {v!r}")
