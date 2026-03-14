from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path("/opt/tak/tools/takctl/web")
USER_UPLOADS_DIR = Path("/opt/tak/tools/takctl/user-uploads")
BRAND_JSON = Path("/opt/tak/tools/takctl/assets/brand.json")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


def mount_static_routes(app: FastAPI) -> None:
    @app.get("/assets/{relpath:path}")
    async def assets(relpath: str):
        if relpath.startswith("/") or relpath.startswith("..") or "/.." in relpath:
            raise HTTPException(status_code=400, detail="bad asset path")

        req_path = (WEB_DIR / "assets" / relpath)
        try:
            resolved = req_path.resolve(strict=True)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not Found")

        assets_root = (WEB_DIR / "assets").resolve()
        uploads_root = USER_UPLOADS_DIR.resolve()

        if not (_is_within(resolved, assets_root) or _is_within(resolved, uploads_root)):
            raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(str(resolved))

    app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
    app.mount("/components", StaticFiles(directory=str(WEB_DIR / "components")), name="components")
    app.mount("/hooks", StaticFiles(directory=str(WEB_DIR / "hooks")), name="hooks")
    app.mount("/vendor", StaticFiles(directory=str(WEB_DIR / "vendor")), name="vendor")

    @app.get("/")
    async def index():
        return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/styles.css")
    async def styles_css():
        return Response((WEB_DIR / "styles.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/app.js")
    async def app_js():
        return Response((WEB_DIR / "app.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/splash.html")
    async def splash_html():
        return HTMLResponse((WEB_DIR / "splash.html").read_text(encoding="utf-8"))

    @app.get("/splash.fragment.html")
    async def splash_fragment_html():
        return HTMLResponse((WEB_DIR / "splash.fragment.html").read_text(encoding="utf-8"))

    @app.head("/splash.fragment.html")
    async def splash_fragment_head():
        return Response(status_code=200)

    @app.get("/splash.css")
    async def splash_css():
        return Response((WEB_DIR / "splash.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.get("/splash.js")
    async def splash_js():
        return Response((WEB_DIR / "splash.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/api/public/brand")
    async def public_brand(unit: str | None = None):
        import json

        candidates = [
            BRAND_JSON,
            (WEB_DIR / "assets" / "brand.json"),
        ]

        for bp in candidates:
            try:
                if bp.exists() and bp.is_file():
                    data = json.loads(bp.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        data = {}
                    login = data.get("login")
                    if not isinstance(login, dict):
                        login = {}
                    data["login"] = login
                    if "role" not in login:
                        login["role"] = False
                    return data
            except Exception:
                raise HTTPException(status_code=500, detail="Invalid brand.json")

        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/u/{unit_path:path}/assets/{relpath:path}")
    async def public_unit_asset(unit_path: str, relpath: str):
        if relpath.startswith("/") or relpath.startswith("..") or "/.." in relpath:
            raise HTTPException(status_code=400, detail="bad asset path")
        if unit_path.startswith("/") or unit_path.startswith("..") or "/.." in unit_path:
            raise HTTPException(status_code=400, detail="bad unit path")

        req_path = (USER_UPLOADS_DIR / unit_path / "assets" / relpath)
        try:
            resolved = req_path.resolve(strict=True)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Not Found")

        uploads_root = USER_UPLOADS_DIR.resolve()
        if not _is_within(resolved, uploads_root):
            raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(str(resolved))
