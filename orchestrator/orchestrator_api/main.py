from __future__ import annotations
from fastapi import FastAPI

from .api_v1 import router as api_v1_router
from .ui import router as ui_router

app = FastAPI(title="taks-orchestrator", version="0.1.0")

# UI + auth-gated routes
app.include_router(ui_router)

# API v1
app.include_router(api_v1_router)

# Legacy API shim (hidden from schema)
from .api_v1 import api_status, nodes_preview, nodes_dry_run, nodes_launch  # noqa: E402
app.add_api_route("/api/status", api_status, methods=["GET"], include_in_schema=False)
app.add_api_route("/api/nodes/preview", nodes_preview, methods=["POST"], include_in_schema=False)
app.add_api_route("/api/nodes/dry-run", nodes_dry_run, methods=["POST"], include_in_schema=False)
app.add_api_route("/api/nodes/launch", nodes_launch, methods=["POST"], include_in_schema=False)
