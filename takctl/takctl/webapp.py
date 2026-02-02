from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from takctl.api.health import router as health_router

app = FastAPI(title="takctl-web")

# API first (so it wins before the catch-all static mount)
app.include_router(health_router, prefix="/api")

# Serve the web UI from takctl/web/
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if WEB_DIR.is_dir():
    # Mount at "/" so index.html is served at "/"
    # and assets resolve as /static/..., /vendor/..., etc.
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
