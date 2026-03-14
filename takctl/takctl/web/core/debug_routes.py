from __future__ import annotations

import traceback
import uuid
from datetime import datetime, timezone
import html as _html
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from takctl.web.core.auth_routes import get_session

_LAST_EXC: Dict[str, Any] = {
    "ts_utc": None,
    "request_id": None,
    "user": None,
    "method": None,
    "path": None,
    "traceback": None,
}


def _wants_html(req: Request) -> bool:
    try:
        a = (req.headers.get("accept") or "").lower()
        return "text/html" in a
    except Exception:
        return False


def _debug_allowed(req: Request) -> bool:
    return get_session(req) is not None


def _taks_error_page(*, status: int, title: str, detail: str, rid: str, tb: str | None) -> HTMLResponse:
    esc = _html.escape
    hdr = esc(title or "Error")
    det = esc(detail or "")
    meta = "request_id=" + esc(rid or "") + "  status=" + str(int(status))
    tb_txt = tb or ""
    tb_html = "<pre>" + esc(tb_txt) + "</pre>" if tb_txt else "<div class=\"muted\">(no traceback)</div>"

    le = _LAST_EXC
    last_meta = "ts_utc={ts}  request_id={rid}  user={u}".format(
        ts=esc(str(le.get("ts_utc") or "")),
        rid=esc(str(le.get("request_id") or "")),
        u=esc(str(le.get("user") or "")),
    )
    last_tb = le.get("traceback") or ""
    last_tb_html = "<pre>" + esc(last_tb) + "</pre>" if last_tb else "<div class=\"muted\">(none captured yet)</div>"

    html = """<!doctype html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{hdr}</title>
<style>
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 18px; background:#0b0d10; color:#e9eef5; }}
  .card {{ background:#10151b; border:1px solid #1f2a33; border-radius:14px; padding:14px; margin: 12px 0; }}
  .muted {{ color:#9fb0c0; font-size: 12px; }}
  h2 {{ margin: 0 0 6px 0; font-size: 18px; }}
  pre {{ white-space: pre-wrap; background: #07090c; color:#d7e1ee; padding: 12px; border-radius: 10px; overflow:auto; border:1px solid #1a222b; }}
  a {{ color:#7db7ff; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
</style>
</head><body>
  <div class="card">
    <h2>{hdr}</h2>
    <div class="muted">{meta}</div>
    <div style="margin-top:10px">{det}</div>
  </div>

  <div class="card">
    <h2>Traceback</h2>
    <div class="muted">Shown only because you are authenticated.</div>
    {tb_html}
  </div>

  <div class="card">
    <h2>Last captured exception</h2>
    <div class="muted">{last_meta}</div>
    {last_tb_html}
    <div class="muted" style="margin-top:8px">
      JSON: <a href="/api/_debug/last_exception?format=json">/api/_debug/last_exception?format=json</a>
    </div>
  </div>
</body></html>
""".format(hdr=hdr, meta=meta, det=det, tb_html=tb_html, last_meta=last_meta, last_tb_html=last_tb_html)

    return HTMLResponse(html, status_code=int(status))


def mount_debug_routes(app: FastAPI) -> None:
    @app.middleware("http")
    async def _taks_capture_last_exception(req: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        try:
            req.state.taks_request_id = rid
        except Exception:
            pass

        try:
            resp = await call_next(req)
            try:
                resp.headers["X-TAKS-Request-Id"] = rid
            except Exception:
                pass
            return resp
        except Exception:
            sess = get_session(req)
            _LAST_EXC.update({
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "request_id": rid,
                "user": (sess or {}).get("u") if sess else None,
                "method": getattr(req, "method", None),
                "path": str(getattr(req, "url", "")),
                "traceback": traceback.format_exc(),
            })
            raise

    @app.get("/api/_debug/last_exception", include_in_schema=False)
    def _debug_last_exception(req: Request):
        sess = get_session(req)
        if not sess:
            raise HTTPException(status_code=401, detail="not authenticated")
        fmt = (req.query_params.get("format") or "").strip().lower()
        if fmt == "json":
            return JSONResponse(_LAST_EXC)
        tb = _LAST_EXC.get("traceback") or "(no exception captured yet)"
        meta = "ts_utc={ts}  request_id={rid}  user={u}".format(
            ts=str(_LAST_EXC.get("ts_utc") or ""),
            rid=str(_LAST_EXC.get("request_id") or ""),
            u=str(_LAST_EXC.get("user") or ""),
        )
        html = "<!doctype html><html><head><meta charset=\"utf-8\"/><title>last_exception</title></head><body>" \
               "<div>" + _html.escape(meta) + "</div><pre>" + _html.escape(tb) + "</pre></body></html>"
        return HTMLResponse(html)

    @app.get("/api/_debug/routes", include_in_schema=False)
    def _debug_routes():
        out = []
        for r in app.router.routes:
            try:
                methods = sorted(list(getattr(r, "methods", []) or []))
                path = getattr(r, "path", None)
                name = getattr(r, "name", None)
                if path:
                    out.append({"path": path, "methods": methods, "name": name})
            except Exception:
                continue
        return {"count": len(out), "routes": out}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _taks_handle_validation(req: Request, exc: RequestValidationError):
        rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
        if _wants_html(req) and _debug_allowed(req):
            return _taks_error_page(status=422, title="422 Validation error", detail=str(exc), rid=rid, tb=None)
        return JSONResponse({"detail": exc.errors(), "request_id": rid}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _taks_handle_starlette_http(req: Request, exc: StarletteHTTPException):
        rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
        if _wants_html(req) and _debug_allowed(req):
            return _taks_error_page(status=int(exc.status_code), title=str(exc.status_code) + " HTTP error", detail=str(exc.detail), rid=rid, tb=None)
        return JSONResponse({"detail": exc.detail, "request_id": rid}, status_code=int(exc.status_code))

    @app.exception_handler(HTTPException)
    async def _taks_handle_fastapi_http(req: Request, exc: HTTPException):
        rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
        if _wants_html(req) and _debug_allowed(req):
            return _taks_error_page(status=int(exc.status_code), title=str(exc.status_code) + " HTTP error", detail=str(exc.detail), rid=rid, tb=None)
        return JSONResponse({"detail": exc.detail, "request_id": rid}, status_code=int(exc.status_code))

    @app.exception_handler(Exception)
    async def _taks_handle_uncaught(req: Request, exc: Exception):
        rid = getattr(getattr(req, "state", None), "taks_request_id", "") or ""
        tb = traceback.format_exc()
        if _wants_html(req) and _debug_allowed(req):
            return _taks_error_page(status=500, title="500 Internal Server Error", detail=str(exc), rid=rid, tb=tb)
        return JSONResponse({"detail": "Internal Server Error", "request_id": rid}, status_code=500)
