from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from orchestrator_core.core import NodeRequest, plan_node, aws_dry_run


app = FastAPI(title="taks-orchestrator", version="0.1.0")


class NodeReq(BaseModel):
    battalion: str = Field(..., examples=["48hvbat"])
    fqdn: str = Field(..., examples=["48hvbat.tak-hv-sandbox.se"])
    hostname: str = Field(..., examples=["tak-48hvbat"])
    name: str = Field(..., examples=["tak-node-48hvbat"])
    instance_type: str = Field("t3.micro")


@app.get("/", response_class=HTMLResponse)
def ui_index():
    # Tiny UI served inline (keeps bootstrap simple). We can later move to /static/.
    return HTMLResponse(content=open("/opt/taks/orchestrator/orchestrator_ui/index.html", "r", encoding="utf-8").read())


@app.post("/api/v1/nodes/preview")
def nodes_preview(req: NodeReq):
    try:
        p = plan_node(NodeRequest(**req.model_dump()))
        return {
            "plan": {k: v for k, v in p.items() if k != "cloud_init"},
            "cloud_init": p["cloud_init"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/nodes/dry-run")
def nodes_dry_run(req: NodeReq):
    try:
        return aws_dry_run(NodeRequest(**req.model_dump()))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/nodes/launch")
def nodes_launch(_req: NodeReq):
    # Guard rail: we intentionally block real launches until we implement:
    # - SG + keypair/SSM strategy
    # - volumes
    # - offline bundle mount/logic
    raise HTTPException(status_code=501, detail="Launch not implemented yet (guard rail). Use /api/nodes/dry-run for now.")

# -------------------------------------------------------------------
# LEGACY API SHIM: /api/nodes/*  (temporary)
# Keep backwards compat for older UI/CLI while we migrate to /api/v1/*.
# Hidden from OpenAPI so new clients don’t copy the old paths.
# -------------------------------------------------------------------
try:
    app.add_api_route("/api/v1/nodes/preview", nodes_preview, methods=["POST"], include_in_schema=False)
    app.add_api_route("/api/v1/nodes/dry-run", nodes_dry_run, methods=["POST"], include_in_schema=False)
    app.add_api_route("/api/v1/nodes/launch", nodes_launch, methods=["POST"], include_in_schema=False)
except NameError as e:
    # If these names differ in your app.py, fix them once and keep this shim.
    raise RuntimeError(f"Legacy shim failed; expected handler names nodes_preview/nodes_dry_run/nodes_launch: {e}")
