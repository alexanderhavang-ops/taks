from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from orchestrator_core.core import NodeRequest
from orchestrator_core.providers import preview_node, dry_run_node, launch_node, status_nodes

from orchestrator_api.auth import verify_cookie, verify_basic


def require_api_auth(req: Request) -> None:
    # Headless-friendly: allow either cookie auth (UI) OR Basic Auth (automation/cloud-init)
    if verify_cookie(req) or verify_basic(req):
        return None
    raise HTTPException(status_code=401, detail="auth required")


router = APIRouter(prefix="/api/v1")


class NodeReq(BaseModel):
    battalion: str = Field(..., examples=["48hvbat"])
    fqdn: str = Field(..., examples=["48hvbat.tak-hv-sandbox.se"])
    hostname: str = Field(..., examples=["tak-48hvbat"])
    name: str = Field(..., examples=["tak-node-48hvbat"])
    instance_type: str = Field("t3.micro")


@router.get("/status")
def api_status():
    try:
        return status_nodes()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/preview", dependencies=[Depends(require_api_auth)])
def nodes_preview(req: NodeReq) -> Dict[str, Any]:
    try:
        p = preview_node(NodeRequest(**req.model_dump()))
        # keep cloud_init separate for UI
        if isinstance(p, dict) and "cloud_init" in p:
            return {"plan": {k: v for k, v in p.items() if k != "cloud_init"}, "cloud_init": p["cloud_init"]}
        return {"plan": p, "cloud_init": ""}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/dry-run", dependencies=[Depends(require_api_auth)])
def nodes_dry_run(req: NodeReq) -> Dict[str, Any]:
    try:
        return dry_run_node(NodeRequest(**req.model_dump()))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/launch", dependencies=[Depends(require_api_auth)])
def nodes_launch(req: NodeReq) -> Dict[str, Any]:
    try:
        return launch_node(NodeRequest(**req.model_dump()))
    except Exception as e:
        msg = str(e)
        if "Launch disabled" in msg:
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
