from __future__ import annotations

from fastapi import FastAPI

from .api_v2 import router as api_v2_router
from .api_v1 import router as api_v1_router
from .ui import router as ui_router
from .public_bundles import router as public_bundles_router
from .units_v2 import router as units_v2_router
from .unit_files_v2 import router as unit_files_v2_router

app = FastAPI(title="taks-orchestrator", version="0.2.0")

# UI
app.include_router(ui_router)

# Public, no-auth bundle downloads (MAXIMUM BORING)
app.include_router(public_bundles_router)

# API v1 (boring/stable; node bootstrap uses this)
app.include_router(api_v1_router)
app.include_router(units_v2_router)
app.include_router(unit_files_v2_router)

# API v2 (authoritative)
app.include_router(api_v2_router)

