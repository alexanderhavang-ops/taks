from __future__ import annotations

from datetime import datetime, timezone
from takctl.onboarding.models import OnboardingRecord, OnboardingStatus, PackageMeta, DeliveryMeta
import json
import hashlib
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urlunparse

from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse, HTMLResponse, RedirectResponse
from takctl.onboarding.service_builder import build_service as _build_service
from takctl.onboarding.qrencode import write_qr_png

from takctl.onboarding.http import external_base, forwarded_host_only, bool_q
from takctl.onboarding.selection import artifact_root, load_selection, save_selection
from takctl.onboarding.atak import (
    atak_enroll_payload,
    atak_enroll_creds_payload,
    atak_package_creds_url,
    atak_package_url,
    itak_package_url,
    qr_payload,
    write_atak_package_zip,
    write_itak_package_zip,
    now_utc_iso,
)
from takctl.onboarding.pages import render_generate_page, render_card_page


router = APIRouter(tags=["onboarding"])

def _external_req_url(req) -> str:
    """Proxy-safe external URL for this request (scheme+host from forwarded headers)."""
    base = external_base(req).rstrip("/")
    path = str(req.url.path)
    q = (str(req.url.query) or "").strip()
    return f"{base}{path}" + (f"?{q}" if q else "")


# --- TAKS onboarding stage-gates helpers ---

def _bundle_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y.%m")

def _sel_hash(sel: dict) -> str:
    try:
        raw = json.dumps(sel or {}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        raw = b"{}"
    return hashlib.sha256(raw).hexdigest()

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _url_with_qs(url: str, **add) -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    for k, v in add.items():
        if v is None:
            continue
        q[str(k)] = str(v)
    new_q = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))

def _get_record(svc, username: str):
    try:
        return svc.store.get_record(username)
    except Exception:
        return None

def _upsert_record(svc, rec: OnboardingRecord) -> None:
    try:
        svc.store.upsert_record(rec)
    except Exception:
        return

def _mark_pending(svc, username: str) -> None:
    rec = _get_record(svc, username)
    if rec is None or rec.status == OnboardingStatus.NEW:
        _upsert_record(svc, OnboardingRecord(username=username, status=OnboardingStatus.PACKAGE_PENDING))

def _mark_qr_generated(svc, username: str) -> None:
    rec = _get_record(svc, username)
    if rec is None:
        rec = OnboardingRecord(username=username, status=OnboardingStatus.NEW)
    dlv0 = rec.delivery or DeliveryMeta()
    dlv = DeliveryMeta(
        qr_generated=True,
        download_url=dlv0.download_url,
        downloaded_at=dlv0.downloaded_at,
        delivery_method="qr",
    )
    _upsert_record(svc, OnboardingRecord(username=username, status=rec.status, package=rec.package, delivery=dlv))

def _mark_package_generated(svc, username: str, *, package_type: str, sel: dict) -> None:
    rec = _get_record(svc, username)
    if rec is None:
        rec = OnboardingRecord(username=username, status=OnboardingStatus.NEW)

    pkg = PackageMeta(
        package_type=package_type,
        version=_bundle_version(),
        generated_at=_now_utc(),
        plugins=[],
        maps=[],
        config_hash=_sel_hash(sel or {}),
    )
    st = rec.status
    if st in (OnboardingStatus.NEW, OnboardingStatus.PACKAGE_PENDING):
        st = OnboardingStatus.PACKAGE_GENERATED
    _upsert_record(svc, OnboardingRecord(username=username, status=st, package=pkg, delivery=rec.delivery))

def _mark_downloaded(svc, username: str, *, download_url: str | None, via: str | None) -> None:
    rec = _get_record(svc, username)
    if rec is None:
        rec = OnboardingRecord(username=username, status=OnboardingStatus.NEW)

    dlv0 = rec.delivery or DeliveryMeta()
    method = "qr" if (via or "").strip().lower() == "qr" else (dlv0.delivery_method or "manual")
    dlv = DeliveryMeta(
        qr_generated=bool(dlv0.qr_generated),
        download_url=download_url or dlv0.download_url,
        downloaded_at=_now_utc(),
        delivery_method=method,
    )
    _upsert_record(svc, OnboardingRecord(username=username, status=OnboardingStatus.DOWNLOADED, package=rec.package, delivery=dlv))

# --- end helpers ---



def _require_user(username: str):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    svc = _build_service()
    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")
    return svc, u, username



# -----------------------------------------------------------------------------
# Token-scoped package + QR endpoints (public, TTL-limited)
# -----------------------------------------------------------------------------

def _require_token(token: str):
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token required")

    svc = _build_service()
    try:
        ct = svc.store.get_card_token(token)
    except Exception:
        raise HTTPException(status_code=404, detail="card token not found")

    # Expiry check (treat expired as gone)
    try:
        exp = getattr(ct, "expires_at_utc", None)
        if exp is not None and exp <= _now_utc():
            raise HTTPException(status_code=410, detail="card token expired")
    except HTTPException:
        raise
    except Exception:
        # If model is unexpected, fail closed
        raise HTTPException(status_code=404, detail="card token invalid")

    username = (getattr(ct, "username", "") or "").strip()
    if not username:
        raise HTTPException(status_code=404, detail="card token missing username")

    u = svc.ud.get_user(username)
    if u is None:
        raise HTTPException(status_code=404, detail=f"user not found in UserAuthenticationFile.xml: {username}")

    return svc, u, username, ct


@router.get("/onboarding/cards/{token}/packages/{client}/qr.txt")
def token_qr_payload_txt(req: Request, token: str, client: str):
    svc, _, username, _ = _require_token(token)
    _mark_qr_generated(svc, username)

    c = (client or "").strip().lower()
    if c not in ("atak", "itak", "wintak"):
        raise HTTPException(status_code=400, detail=f"unknown client: {client}")

    base = _resolve_public_base(req, username)
    package_url = f"{base}/api/onboarding/cards/{token}/packages/{c}/package.zip"
    package_url = _url_with_qs(package_url, via="qr")

    host, port, use_ssl = _resolve_qr_endpoint(req, username, c)
    payload = qr_payload(c, package_url, host, port=port, use_ssl=use_ssl)

    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/cards/{token}/card-url/qr.txt")
def token_card_url_qr_txt(req: Request, token: str):
    _, _, username, _ = _require_token(token)
    base = external_base(req)
    payload = f"{base}/api/onboarding/cards/{token}"
    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/cards/{token}/card-url/qr.png")
def token_card_url_qr_png(req: Request, token: str):
    _, _, username, _ = _require_token(token)
    base = external_base(req)
    payload = f"{base}/api/onboarding/cards/{token}"
    out = artifact_root(username) / f"{username}.card-url.qr.png"
    write_qr_png(payload, out, size=8)
    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.card-url.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/cards/{token}/packages/{client}/qr.png")
def token_qr_png(req: Request, token: str, client: str):
    svc, _, username, _ = _require_token(token)
    _mark_qr_generated(svc, username)

    c = (client or "").strip().lower()
    if c not in ("atak", "itak", "wintak"):
        raise HTTPException(status_code=400, detail=f"unknown client: {client}")

    base = _resolve_public_base(req, username)
    package_url = f"{base}/api/onboarding/cards/{token}/packages/{c}/package.zip"
    package_url = _url_with_qs(package_url, via="qr")

    host, port, use_ssl = _resolve_qr_endpoint(req, username, c)
    payload = qr_payload(c, package_url, host, port=port, use_ssl=use_ssl)

    out = artifact_root(username) / f"{username}.{c}.token.qr.png"
    write_qr_png(payload, out, size=8)

    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.{c}.token.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/cards/{token}/packages/atak/package.zip")
def token_atak_package_zip(req: Request, token: str):
    svc, _, username, _ = _require_token(token)

    out = artifact_root(username) / "atak" / "package.zip"
    regen = (req.query_params.get("regen") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    base = external_base(req)
    if regen or (not out.exists()):
        write_atak_package_zip(out, username, req, include_creds=False, base=base)
        _mark_package_generated(svc, username, package_type="atak", sel=(load_selection(username) or {}))

    via = (req.query_params.get("via") or "").strip()
    _mark_downloaded(svc, username, download_url=_external_req_url(req), via=via)

    return FileResponse(
        str(out),
        media_type="application/zip",
        filename=f"{username}.atak.package.zip",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


def _resolve_public_base(req: Request, username: str) -> str:
    sel = load_selection(username) or {}
    ep = dict((sel.get("endpoints") or {})) if isinstance(sel, dict) else {}

    scheme = (
        (req.query_params.get("public_scheme") or "").strip()
        or "https"
    )

    host = (
        (req.query_params.get("public_host") or "").strip()
        or str(ep.get("stream_host") or "").strip()
        or forwarded_host_only(req)
    )

    return f"{scheme}://{host}"


def _resolve_qr_endpoint(req: Request, username: str, client: str) -> tuple[str, int | None, bool | None]:
    c = (client or "").strip().lower()
    if c != "itak":
        return forwarded_host_only(req), None, None

    sel = load_selection(username) or {}
    ep = dict((sel.get("endpoints") or {})) if isinstance(sel, dict) else {}

    host = (
        (req.query_params.get("host") or "").strip()
        or str(ep.get("enroll_host") or "").strip()
        or str(ep.get("stream_host") or "").strip()
        or forwarded_host_only(req)
    )

    raw_port = (req.query_params.get("port") or "").strip()
    if raw_port:
        try:
            port = int(raw_port)
        except Exception:
            port = 8446
    else:
        try:
            port = int(str(ep.get("enroll_port") or "").strip() or "8446")
        except Exception:
            port = 8446

    ssl_raw = req.query_params.get("ssl")
    if ssl_raw is not None and str(ssl_raw).strip():
        use_ssl = bool_q(req, "ssl", True)
    else:
        use_ssl = str(ep.get("enroll_ssl") or "true").strip().lower() in ("1", "true", "yes", "y", "on")

    return host, port, use_ssl


@router.get("/onboarding/cards/{token}/packages/itak/package.zip")
def token_itak_package_zip(req: Request, token: str):
    svc, _, username, _ = _require_token(token)

    out = artifact_root(username) / "itak" / "package.zip"
    regen = (req.query_params.get("regen") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    base = _resolve_public_base(req, username)
    if regen or (not out.exists()):
        write_itak_package_zip(out, username, req, base=base)
        _mark_package_generated(svc, username, package_type="itak", sel=(load_selection(username) or {}))

    via = (req.query_params.get("via") or "").strip()
    _mark_downloaded(svc, username, download_url=_external_req_url(req), via=via)

    return FileResponse(
        str(out),
        media_type="application/zip",
        filename=f"{username}.itak.package.zip",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/users/{username}/packages/itak/package.zip")
def itak_package_zip(req: Request, username: str):
    svc, _, username = _require_user(username)

    out = artifact_root(username) / "itak" / "package.zip"
    regen = (req.query_params.get("regen") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    base = _resolve_public_base(req, username)
    if regen or (not out.exists()):
        write_itak_package_zip(out, username, req, base=base)
        _mark_package_generated(svc, username, package_type="itak", sel=(load_selection(username) or {}))

    via = (req.query_params.get("via") or "").strip()
    _mark_downloaded(svc, username, download_url=_external_req_url(req), via=via)

    return FileResponse(
        str(out),
        media_type="application/zip",
        filename=f"{username}.itak.package.zip",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


# -----------------------------------------------------------------------------
# Generic QR endpoints (atak/itak/wintak)
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/{client}/qr.txt")
def qr_payload_txt(req: Request, username: str, client: str):
    svc, _, username = _require_user(username)
    _mark_qr_generated(svc, username)
    c = (client or "").strip().lower()
    if c not in ("atak", "itak", "wintak"):
        raise HTTPException(status_code=400, detail=f"unknown client: {client}")

    base = _resolve_public_base(req, username)
    package_url = _url_with_qs((itak_package_url(base, username) if c == "itak" else atak_package_url(base, username)), via="qr")
    host, port, use_ssl = _resolve_qr_endpoint(req, username, c)
    payload = qr_payload(c, package_url, host, port=port, use_ssl=use_ssl)

    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/users/{username}/packages/{client}/qr.payload.json")
def qr_payload_json(req: Request, username: str, client: str):
    svc, _, username = _require_user(username)
    _mark_qr_generated(svc, username)
    c = (client or "").strip().lower()
    if c not in ("atak", "itak", "wintak"):
        raise HTTPException(status_code=400, detail=f"unknown client: {client}")

    base = _resolve_public_base(req, username)
    package_url = _url_with_qs((itak_package_url(base, username) if c == "itak" else atak_package_url(base, username)), via="qr")
    host, port, use_ssl = _resolve_qr_endpoint(req, username, c)
    payload = qr_payload(c, package_url, host, port=port, use_ssl=use_ssl)

    return JSONResponse(
        {"client": c, "host": host, "port": port, "ssl": use_ssl, "package_url": package_url, "qr_payload": payload},
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/users/{username}/packages/{client}/qr.png")
def qr_png(req: Request, username: str, client: str):
    svc, _, username = _require_user(username)
    _mark_qr_generated(svc, username)
    c = (client or "").strip().lower()
    if c not in ("atak", "itak", "wintak"):
        raise HTTPException(status_code=400, detail=f"unknown client: {client}")

    base = _resolve_public_base(req, username)
    package_url = _url_with_qs((itak_package_url(base, username) if c == "itak" else atak_package_url(base, username)), via="qr")
    host, port, use_ssl = _resolve_qr_endpoint(req, username, c)
    payload = qr_payload(c, package_url, host, port=port, use_ssl=use_ssl)

    out = artifact_root(username) / f"{username}.{c}.qr.png"
    write_qr_png(payload, out, size=8)

    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.{c}.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


# -----------------------------------------------------------------------------
# Path A: enroll (passwordless) - experimental
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/atak/enroll/qr.txt")
def atak_enroll_qr_txt(req: Request, username: str):
    _, _, username = _require_user(username)
    payload = atak_enroll_payload(req)
    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/users/{username}/packages/atak/enroll/qr.png")
def atak_enroll_qr_png(req: Request, username: str):
    _, _, username = _require_user(username)
    payload = atak_enroll_payload(req)
    out = artifact_root(username) / f"{username}.atak.enroll.qr.png"
    write_qr_png(payload, out, size=8)
    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.atak.enroll.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


# -----------------------------------------------------------------------------
# Path C: enroll + creds (experimental helper page + qr)
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/atak/enroll-creds/qr.txt")
def atak_enroll_creds_qr_txt(req: Request, username: str):
    _, _, username = _require_user(username)
    payload = atak_enroll_creds_payload(req, username)
    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/users/{username}/packages/atak/enroll-creds/qr.png")
def atak_enroll_creds_qr_png(req: Request, username: str):
    _, _, username = _require_user(username)
    payload = atak_enroll_creds_payload(req, username)
    out = artifact_root(username) / f"{username}.atak.enroll-creds.qr.png"
    write_qr_png(payload, out, size=8)
    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.atak.enroll-creds.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/users/{username}/packages/atak/enroll-creds")
def atak_enroll_creds_page(req: Request, username: str):
    """
    Helper page for Path C. Uses ?password= for convenience.
    Prefer header x-taks-password when you hit /qr.png directly.
    """
    _, _, username = _require_user(username)
    base = external_base(req)
    bump = int(datetime.now(timezone.utc).timestamp())

    enroll_host = (req.query_params.get("enroll_host") or forwarded_host_only(req)).strip()
    enroll_port = (req.query_params.get("enroll_port") or "").strip()
    enroll_ssl  = (req.query_params.get("enroll_ssl") or "true").strip()
    pw = (req.query_params.get("password") or "").strip()

    img = ""
    if pw:
        parts = [
            f"{base}/api/onboarding/users/{username}/packages/atak/enroll-creds/qr.png",
            f"?b={bump}",
            f"&enroll_host={quote(enroll_host, safe='')}",
            f"&enroll_ssl={quote(enroll_ssl, safe='')}",
        ]
        if enroll_port:
            parts.append(f"&enroll_port={quote(enroll_port, safe='')}")
        parts.append(f"&password={quote(pw, safe='')}")
        img_url = "".join(parts)
        img = f'<div class="qr"><img alt="ATAK Enroll+Creds QR" src="{img_url}"/></div>'

    html = f"""<!doctype html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ATAK Enroll+Creds QR – {username}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 22px; }}
h1 {{ font-size: 18px; margin: 0 0 10px 0; }}
.note {{ font-size: 13px; color: #444; line-height: 1.35; margin-bottom: 12px; }}
form {{ display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap; }}
label {{ font-size: 12px; color:#333; display:flex; flex-direction:column; gap:6px; }}
input {{ padding: 8px 10px; border:1px solid #ddd; border-radius:10px; min-width: 240px; }}
button {{ padding: 9px 12px; border:1px solid #ccc; border-radius:10px; background:#f7f7f7; cursor:pointer; }}
.qr {{ margin-top: 14px; padding: 12px; border: 1px dashed #ddd; border-radius: 14px; display:flex; justify-content:center; background:#fff; }}
.qr img {{ width: 280px; height: 280px; image-rendering: pixelated; }}
small {{ color:#666; }}
code {{ background:#f5f5f5; border:1px solid #eee; border-radius:6px; padding:2px 6px; }}
</style>
</head>
<body>
<h1>Path C — ATAK Enroll QR (includes creds)</h1>
<div class="note">
Experimental. Password is not stored by TAKS; it is only used to render the QR.
<br/><small>Note: this uses <code>?password=</code> in the URL on this page.</small>
</div>

<form method="get">
  <label>Password
    <input name="password" type="password" value="{pw}"/>
  </label>
  <label>Enroll host
    <input name="enroll_host" value="{enroll_host}"/>
  </label>
  <label>Enroll port (optional)
    <input name="enroll_port" value="{enroll_port}"/>
  </label>
  <label>SSL
    <input name="enroll_ssl" value="{enroll_ssl}"/>
  </label>
  <button type="submit">Generate QR</button>
</form>

{img}

</body></html>
"""
    return HTMLResponse(html, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


# -----------------------------------------------------------------------------
# Package QR endpoints (atak package-creds import QR)
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/atak/package-creds/qr.txt")
def atak_package_creds_qr_txt(req: Request, username: str):
    _, _, username = _require_user(username)
    base = external_base(req)
    url = atak_package_creds_url(base, username)
    pw = (req.query_params.get("password") or "").strip()
    if pw:
        url = url + "&password=" + quote(pw, safe="")
    payload = "tak://com.atakmap.app/import?url=" + quote(url, safe="")
    return PlainTextResponse(payload + "\n", headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.get("/onboarding/users/{username}/packages/atak/package-creds/qr.png")
def atak_package_creds_qr_png(req: Request, username: str):
    _, _, username = _require_user(username)
    base = external_base(req)
    url = atak_package_creds_url(base, username)
    pw = (req.query_params.get("password") or "").strip()
    if pw:
        url = url + "&password=" + quote(pw, safe="")
    payload = "tak://com.atakmap.app/import?url=" + quote(url, safe="")
    out = artifact_root(username) / f"{username}.atak.package-creds.qr.png"
    write_qr_png(payload, out, size=8)
    return FileResponse(
        str(out),
        media_type="image/png",
        filename=f"{username}.atak.package-creds.qr.png",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


# -----------------------------------------------------------------------------
# Package download endpoints
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/atak/package.zip")
def atak_package_zip(req: Request, username: str):
    svc, _, username = _require_user(username)
    out = artifact_root(username) / "atak" / "package.zip"
    regen = (req.query_params.get("regen") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    base = external_base(req)
    if regen or (not out.exists()):
        write_atak_package_zip(out, username, req, include_creds=False, base=base)
        _mark_package_generated(svc, username, package_type="atak", sel=(load_selection(username) or {}))
    # Stage-gate: serving package counts as download
    via = (req.query_params.get("via") or "").strip()
    _mark_downloaded(svc, username, download_url=_external_req_url(req), via=via)
    return FileResponse(
        str(out),
        media_type="application/zip",
        filename=f"{username}.atak.package.zip",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


@router.get("/onboarding/users/{username}/packages/atak/package-creds/package.zip")
def atak_package_creds_zip(req: Request, username: str):
    svc, _, username = _require_user(username)
    out = artifact_root(username) / "atak" / "package-creds.zip"
    regen = (req.query_params.get("regen") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    base = external_base(req)
    if regen or (not out.exists()):
        write_atak_package_zip(out, username, req, include_creds=True, base=base)
        _mark_package_generated(svc, username, package_type="atak", sel=(load_selection(username) or {}))
    # Stage-gate: serving package counts as download
    via = (req.query_params.get("via") or "").strip()
    _mark_downloaded(svc, username, download_url=_external_req_url(req), via=via)
    return FileResponse(
        str(out),
        media_type="application/zip",
        filename=f"{username}.atak.package-creds.zip",
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )


# -----------------------------------------------------------------------------
# Generate + Card pages
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/generate")
def onboarding_generate_page(req: Request, username: str):
    _, u, username = _require_user(username)
    base = external_base(req)
    sel = load_selection(username) or {}
    html = render_generate_page(username=username, groups=list(u.groups), base=base, sel=sel)
    return HTMLResponse(html, headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"})


@router.post("/onboarding/users/{username}/generate/submit")
def onboarding_generate_submit(
    req: Request,
    username: str,
    path_A: str | None = Form(default=None),
    path_B: str | None = Form(default=None),
    path_C: str | None = Form(default=None),
    path_itak: str | None = Form(default=None),
    path_wintak: str | None = Form(default=None),
    policy_id: str = Form(default="hemvarnet"),
    unit: str = Form(default=""),
    n: str = Form(default=""),
    role: str = Form(default="member"),
    company: str = Form(default=""),
    platoon: str = Form(default=""),
    enroll_host: str = Form(default=""),
    enroll_port: str = Form(default="8446"),
    enroll_ssl: str = Form(default="true"),
    stream_host: str = Form(default=""),
    stream_port: str = Form(default="8089"),
    stream_ssl: str = Form(default="true"),
):
    _, _, username = _require_user(username)

    paths = {
        "A": bool(path_A),
        "B": bool(path_B),
        "C": bool(path_C),
        "itak": bool(path_itak),
        "wintak": bool(path_wintak),
    }

    sel = {
        "generated_at_utc": now_utc_iso(),
        "paths": paths,
        "ctx": {
            "policy_id": (policy_id or "hemvarnet").strip(),
            "unit": (unit or "").strip(),
            "n": (n or "").strip(),
            "role": (role or "member").strip(),
            "company": (company or "").strip(),
            "platoon": (platoon or "").strip(),
        },
        "endpoints": {
            "enroll_host": (enroll_host or forwarded_host_only(req)).strip(),
            "enroll_port": (enroll_port or "8446").strip(),
            "enroll_ssl": (enroll_ssl or "true").strip(),
            "stream_host": (stream_host or forwarded_host_only(req)).strip(),
            "stream_port": (stream_port or "8089").strip(),
            "stream_ssl": (stream_ssl or "true").strip(),
        },
    }
    save_selection(username, sel)

    base = external_base(req)
    return RedirectResponse(url=f"{base}/api/onboarding/users/{username}/card", status_code=303)


@router.get("/onboarding/users/{username}/card")
def onboarding_card(req: Request, username: str):
    # Admin entry point: issue a short-lived public soldier card and redirect to it.
    svc, u, username = _require_user(username)

    # Default TTL: 10 minutes. (Admin can re-open 'Card' to re-issue.)
    ttl_sec = 600

    # Safe default: request reveal_password=True, but soldier page will only show
    # a password if TAKS actually knows it (origin=taks + password_known).
    # Prefer store compat wrapper (ttl_sec), fall back to issue_card_token(ttl_hours)
    if hasattr(svc.store, "create_card_token"):
        ct = svc.store.create_card_token(username=username, ttl_sec=ttl_sec, reveal_password=True)
    else:
        ttl_hours = max(1, int((int(ttl_sec) + 3599) // 3600))
        ct = svc.store.issue_card_token(username=username, ttl_hours=ttl_hours, reveal_password=True)


    base = external_base(req).rstrip("/")
    return RedirectResponse(url=f"{base}/api/onboarding/cards/{ct.token}", status_code=303)


# -----------------------------------------------------------------------------
# Preview (optional convenience)
# -----------------------------------------------------------------------------

@router.get("/onboarding/users/{username}/packages/preview")
def preview_packages(username: str):
    _, u, username = _require_user(username)

    matrix = [
        {"client": "atak", "notes": "ATAK import QR -> downloads package.zip (config.pref)."},
        {"client": "atak_enroll", "notes": "ATAK enroll deeplink QR (passwordless)."},
        {"client": "atak_package_creds", "notes": "ATAK import package with experimental hook."},
        {"client": "itak", "notes": "iTAK quick connect QR text line."},
        {"client": "wintak", "notes": "WinTAK URL fallback QR."},
    ]

    return JSONResponse(
        {"user": {"username": username, "groups": list(u.groups)}, "packages": matrix},
        headers={"cache-control": "no-store, max-age=0", "pragma": "no-cache"},
    )
