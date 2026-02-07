from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from orchestrator_api.auth import verify_basic_auth, verify_token
from orchestrator_core.core import NodeRequest
<<<<<<< HEAD
from orchestrator_core.providers import dry_run_node, launch_node, preview_node, status_nodes
=======
from orchestrator_core.providers import (
    preview_node,
    dry_run_node,
    launch_node,
    status_nodes,
)
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)

router = APIRouter(prefix="/api/v1")


<<<<<<< HEAD
def require_api_auth(req: Request) -> None:
    """
    Accept either:
      - Basic auth (Authorization: Basic ...) using TAKS_API_PASSWORD (fallback TAKS_UI_PASSWORD)
      - Cookie auth (taks_auth) using TAKS_UI_SECRET
    """

    # 1) Basic auth for headless/cloud-init callers
    if verify_basic_auth(req.headers.get("authorization")):
        return None

    # 2) Cookie auth for UI sessions
=======
# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_api_auth(req: Request) -> None:
    """
    Accept either:
      1) Basic auth (headless, cloud-init, curl)
      2) Cookie auth (Web UI)
    """

    # 1) Basic auth
    if verify_basic_auth(req.headers.get("authorization")):
        return None

    # 2) Cookie auth
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
    secret = os.getenv("TAKS_UI_SECRET", "")
    tok = req.cookies.get("taks_auth")
    if secret and tok and verify_token(tok, secret):
        return None

    raise HTTPException(status_code=401, detail="auth required")

<<<<<<< HEAD
=======

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)

@router.get("/status")
def api_status() -> Dict[str, Any]:
    try:
        return status_nodes()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/preview", dependencies=[Depends(require_api_auth)])
def nodes_preview(req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return preview_node(NodeRequest(**req))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/dry-run", dependencies=[Depends(require_api_auth)])
def nodes_dry_run(req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return dry_run_node(NodeRequest(**req))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/launch", dependencies=[Depends(require_api_auth)])
def nodes_launch(req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return launch_node(NodeRequest(**req))
    except Exception as e:
        msg = str(e)
        if "Launch disabled" in msg:
            raise HTTPException(status_code=403, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
<<<<<<< HEAD
<<<<<<< HEAD

=======
>>>>>>> 2233bb7 (orchestrator api: return 403 when launch is disabled)
=======

>>>>>>> 39e1394 (orchestrator: fix auth imports, headless basic auth, installer env load, LE preflight)
