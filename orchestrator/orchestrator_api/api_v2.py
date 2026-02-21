# orchestrator/orchestrator_api/api_v2.py
from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from orchestrator_core.core import NodeRequest, aws_dry_run, aws_launch, aws_list_nodes, plan_node
from orchestrator_core.nodes_state import list_nodes, touch_heartbeat, upsert_node

from .auth import verify_token
from .bundles_v2 import STATIC_BUNDLE_NAME, bundle_dir, ensure_static_bundle

router = APIRouter(prefix="/api/v2")


# ----------------------------
# Auth: allow either UI session cookie OR BASIC (for nodes)
# ----------------------------
def _cookie_auth_ok(request: Request) -> bool:
    secret = (os.environ.get("TAKS_UI_SECRET") or "").strip()
    if not secret:
        return False
    tok = request.cookies.get("taks_auth") or ""
    return bool(tok and verify_token(tok, secret))


def _basic_auth_ok(request: Request) -> bool:
    want_user = (os.environ.get("TAKS_UI_USER") or "orchestrator").strip()
    want_pass = (os.environ.get("TAKS_UI_PASSWORD") or "changeme").strip()

    h = request.headers.get("authorization") or ""
    if not h.lower().startswith("basic "):
        return False

    b64 = h.split(None, 1)[1].strip()
    try:
        raw = base64.b64decode(b64).decode("utf-8", errors="strict")
    except Exception:
        return False

    if ":" not in raw:
        return False

    user, pw = raw.split(":", 1)
    return user == want_user and pw == want_pass


def require_operator(request: Request) -> None:
    if _cookie_auth_ok(request) or _basic_auth_ok(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized (session cookie or BASIC auth required)")


# ----------------------------
# Request normalization (v1 compat + defaults)
# ----------------------------
def _normalize_node_req(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    v2 canonical request:
      unit_path, role, fqdn, hostname, name, instance_type, aws_key_name, bundle_name, bundle_ttl

    Backward compat:
      battalion => unit_path
    """
    d = dict(req or {})

    if "unit_path" not in d and "battalion" in d:
        d["unit_path"] = str(d.pop("battalion"))

    unit_path = str(d.get("unit_path") or "").strip()
    if not unit_path:
        raise HTTPException(status_code=400, detail="Missing unit_path")

    role = str(d.get("role") or "tak-node").strip()
    d["role"] = role

    # hostname default: stable + DNS-safe-ish
    if not str(d.get("hostname") or "").strip():
        safe = unit_path.replace("/", "-").replace("_", "-")
        d["hostname"] = f"tak-{safe}" if safe else "tak-node"

    # name default: AWS tag Name (default to hostname)
    if not str(d.get("name") or "").strip():
        d["name"] = str(d.get("hostname") or "tak-node")

    # fqdn default: best-effort if caller didn't provide one
    if not str(d.get("fqdn") or "").strip():
        base = os.environ.get("TAKS_DEFAULT_NODE_DOMAIN") or "tak-hv-sandbox.se"
        if unit_path and "." in unit_path:
            d["fqdn"] = unit_path
        else:
            d["fqdn"] = f"{unit_path}.{base}"

    # bundle: default to a stable orchestrator-built bundle file name
    if not str(d.get("bundle_name") or "").strip():
        d["bundle_name"] = STATIC_BUNDLE_NAME

    return d


def _node_req(req: Dict[str, Any]) -> NodeRequest:
    d = _normalize_node_req(req)
    try:
        return NodeRequest(**d)
    except TypeError as e:
        # Defensive: surface clean error instead of 500 tracebacks.
        raise HTTPException(status_code=400, detail=f"Invalid node request: {e}")


# ----------------------------
# Status (no auth)
# ----------------------------
@router.get("/status")
def api_status() -> Dict[str, Any]:
    out = aws_list_nodes()
    if not isinstance(out, dict):
        out = {"provider": "aws", "error": "unexpected aws_list_nodes() response"}

    out["launch_enabled"] = (os.environ.get("TAKS_LAUNCH_ENABLED") == "1")

    p = bundle_dir() / STATIC_BUNDLE_NAME
    out["static_bundle"] = {"name": STATIC_BUNDLE_NAME, "path": str(p), "exists": p.exists()}

    return out


# ----------------------------
# Nodes: preview / dry-run / launch (operator auth)
# ----------------------------
@router.post("/nodes/preview")
def nodes_preview(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    nr = _node_req(req)

    # Ensure static bundle exists before we generate cloud-init that references it.
    ensure_static_bundle(nr.unit_path, nr.role)

    plan = plan_node(nr)
    return {
        "plan": {k: plan.get(k) for k in ("region", "ami", "vpc_id", "subnet_id", "instance_type", "tags") if k in plan},
        "cloud_init": plan.get("cloud_init", ""),
        "raw": plan,
    }


@router.post("/nodes/dry-run")
def nodes_dry_run(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    nr = _node_req(req)
    ensure_static_bundle(nr.unit_path, nr.role)
    return aws_dry_run(nr)


@router.post("/nodes/launch")
def nodes_launch(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    if os.environ.get("TAKS_LAUNCH_ENABLED") != "1":
        raise HTTPException(status_code=400, detail="Launch disabled (set TAKS_LAUNCH_ENABLED=1)")
    nr = _node_req(req)
    ensure_static_bundle(nr.unit_path, nr.role)
    return aws_launch(nr)


# ----------------------------
# Running nodes: state DB (operator auth)
# ----------------------------
@router.get("/nodes")
def nodes_list(request: Request) -> Dict[str, Any]:
    require_operator(request)
    items = list_nodes()
    return {"count": len(items), "items": items}


# ----------------------------
# Node -> orchestrator registration/heartbeat
# (allows BASIC auth; also allows cookie auth for convenience)
# ----------------------------
@router.post("/nodes/register")
def nodes_register(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)

    node_id = (req.get("instance_id") or req.get("node_id") or req.get("fqdn") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="missing instance_id/node_id/fqdn")

    patch = {
        "node_id": node_id,
        "instance_id": req.get("instance_id"),
        "unit_path": req.get("unit_path"),
        "role": req.get("role"),
        "fqdn": req.get("fqdn"),
        "hostname": req.get("hostname"),
        "private_ip": req.get("private_ip"),
        "public_ip": req.get("public_ip"),
        "public_dns": req.get("public_dns"),
        "region": req.get("region"),
        "status": req.get("status") or "registered",
        "last_seen_ts": int(time.time()),
        "meta": req.get("meta") if isinstance(req.get("meta"), dict) else None,
    }
    rec = upsert_node(node_id, patch)
    return {"ok": True, "node": rec}


@router.post("/nodes/heartbeat")
def nodes_heartbeat(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)

    node_id = (req.get("instance_id") or req.get("node_id") or req.get("fqdn") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="missing instance_id/node_id/fqdn")

    status = (req.get("status") or "online").strip()
    extra = {}
    for k in ("private_ip", "public_ip", "public_dns", "fqdn", "hostname"):
        if k in req:
            extra[k] = req.get(k)

    rec = touch_heartbeat(node_id, status=status, extra=extra)
    return {"ok": True, "node_id": node_id, "last_seen_ts": rec.get("last_seen_ts"), "status": rec.get("status")}

