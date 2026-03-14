# orchestrator/orchestrator_api/api_v2.py
from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from orchestrator_core.core import NodeRequest, aws_dry_run, aws_launch, aws_list_nodes, aws_terminate, plan_node
from orchestrator_core.nodes_state import get_node, list_nodes, touch_heartbeat, upsert_node
from orchestrator_core.units_state import list_units, create_unit

from .auth import verify_token
from .bundles_v2 import bundle_name_for_unit, bundle_dir, ensure_unit_bundle

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

    if not str(d.get("hostname") or "").strip():
        safe = unit_path.replace("/", "-").replace("_", "-")
        d["hostname"] = f"tak-{safe}" if safe else "tak-node"

    if not str(d.get("name") or "").strip():
        d["name"] = str(d.get("hostname") or "tak-node")

    if not str(d.get("fqdn") or "").strip():
        base = os.environ.get("TAKS_DEFAULT_NODE_DOMAIN") or "tak-hv-sandbox.se"
        if unit_path and "." in unit_path:
            d["fqdn"] = unit_path
        else:
            d["fqdn"] = f"{unit_path}.{base}"

    if not str(d.get("bundle_name") or "").strip():
        d["bundle_name"] = bundle_name_for_unit(unit_path)

    return d


def _node_req(req: Dict[str, Any]) -> NodeRequest:
    d = _normalize_node_req(req)
    try:
        return NodeRequest(**d)
    except TypeError as e:
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
    out["bundle_dir"] = str(bundle_dir())
    return out


# ----------------------------
# Nodes: preview / dry-run / launch (operator auth)
# ----------------------------
@router.post("/nodes/preview")
def nodes_preview(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    nr = _node_req(req)

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
    return aws_dry_run(nr)


@router.post("/nodes/launch")
def nodes_launch(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)
    if os.environ.get("TAKS_LAUNCH_ENABLED") != "1":
        raise HTTPException(status_code=400, detail="Launch disabled (set TAKS_LAUNCH_ENABLED=1)")
    nr = _node_req(req)
    ensure_unit_bundle(nr.unit_path, nr.role)

    launch = aws_launch(nr)
    instance_id = str(launch.get("instance_id") or "").strip()
    if not instance_id:
        raise HTTPException(status_code=500, detail="launch returned no instance_id")

    node_id = str(nr.fqdn or "").strip()
    if not node_id:
        raise HTTPException(status_code=500, detail="launch resolved no fqdn/node_id")

    patch = {
        "node_id": node_id,
        "instance_id": instance_id,
        "unit_path": nr.unit_path,
        "role": nr.role,
        "fqdn": nr.fqdn,
        "hostname": nr.hostname,
        "region": launch.get("region"),
        "status": "booting",
        "aws_state": launch.get("state"),
        "last_seen_ts": None,
        "meta": {
            "launch_source": "api_v2",
            "name": nr.name,
            "instance_type": nr.instance_type,
            "subnet_id": launch.get("subnet_id"),
            "sg_id": launch.get("sg_id"),
        },
    }
    rec = upsert_node(node_id, patch)
    return {"ok": True, "launch": launch, "node": rec}


# ----------------------------
# Running nodes: state DB (operator auth)
# ----------------------------

@router.post("/nodes/{node_id}/terminate")
def nodes_terminate(node_id: str, request: Request) -> Dict[str, Any]:
    require_operator(request)

    rec = get_node(node_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"node not found: {node_id}")

    instance_id = str((rec.get("instance_id") or "")).strip()
    if not instance_id:
        raise HTTPException(status_code=400, detail=f"node has no instance_id: {node_id}")

    term = aws_terminate(instance_id)

    patch = {
        "node_id": rec.get("node_id") or node_id,
        "instance_id": instance_id,
        "status": "terminating",
        "aws_state": term.get("current_state") or "terminating",
    }
    updated = upsert_node(str(rec.get("node_id") or node_id), patch)
    return {"ok": True, "terminate": term, "node": updated}


@router.get("/nodes")
def nodes_list(request: Request) -> Dict[str, Any]:
    require_operator(request)

    items = list_nodes()
    aws = aws_list_nodes()
    aws_instances = list(aws.get("instances") or [])

    aws_by_id = {i.get("instance_id"): i for i in aws_instances if i.get("instance_id")}
    aws_by_pub = {i.get("public_ip"): i for i in aws_instances if i.get("public_ip")}
    aws_by_priv = {i.get("private_ip"): i for i in aws_instances if i.get("private_ip")}

    now = int(time.time())
    out = []

    for n in items:
        row = dict(n)

        inst_id = (row.get("instance_id") or "").strip()
        node_id = (row.get("node_id") or "").strip()

        if not inst_id and node_id.startswith("i-"):
            inst_id = node_id
            row["instance_id"] = inst_id

        if node_id == "tak-orchestrator" and not inst_id:
            row["aws_state"] = "local"
            row["heartbeat_age_sec"] = (now - int(row.get("last_seen_ts") or 0)) if row.get("last_seen_ts") else None
            row["derived_status"] = "local"
            out.append(row)
            continue

        last_seen = int(row.get("last_seen_ts") or 0)
        heartbeat_age = (now - last_seen) if last_seen else None

        aws_rec = None
        if inst_id and inst_id in aws_by_id:
            aws_rec = aws_by_id.get(inst_id)
        else:
            pub = (row.get("public_ip") or "").strip()
            priv = (row.get("private_ip") or "").strip()
            aws_rec = aws_by_pub.get(pub) or aws_by_priv.get(priv)

        if aws_rec is None:
            aws_state = "terminated" if inst_id else "unknown"
        else:
            aws_state = (aws_rec or {}).get("state") or "unknown"

        if aws_state == "terminated":
            derived = "terminated"
        elif aws_state == "stopped":
            derived = "stopped"
        elif aws_state == "running":
            if heartbeat_age is None:
                if row.get("status") == "booting" or last_seen == 0:
                    derived = "booting"
                else:
                    derived = "running"
            elif heartbeat_age > 120:
                derived = "stale"
            else:
                derived = "running"
        else:
            derived = "unknown"

        row["aws_state"] = aws_state
        row["heartbeat_age_sec"] = heartbeat_age
        row["derived_status"] = derived

        if aws_rec:
            row["aws_instance_id"] = aws_rec.get("instance_id")
            row["aws_private_ip"] = aws_rec.get("private_ip")
            row["aws_public_ip"] = aws_rec.get("public_ip")

            if aws_rec.get("instance_id"):
                row["instance_id"] = aws_rec.get("instance_id")
            if aws_rec.get("public_ip"):
                row["public_ip"] = aws_rec.get("public_ip")
            if aws_rec.get("private_ip"):
                row["private_ip"] = aws_rec.get("private_ip")

        out.append(row)

    tracked_ids = {str((x.get("instance_id") or "")).strip() for x in out if str((x.get("instance_id") or "")).strip()}

    for aws_rec in aws_instances:
        inst_id = str(aws_rec.get("instance_id") or "").strip()
        if not inst_id or inst_id in tracked_ids:
            continue

        row = {
            "node_id": inst_id,
            "instance_id": inst_id,
            "unit_path": aws_rec.get("unit_path") or "",
            "role": aws_rec.get("role") or "",
            "fqdn": "",
            "hostname": aws_rec.get("name") or "",
            "public_dns": aws_rec.get("public_dns") or "",
            "public_ip": aws_rec.get("public_ip") or "",
            "private_ip": aws_rec.get("private_ip") or "",
            "aws_state": aws_rec.get("state") or "unknown",
            "derived_status": "untracked",
            "last_seen_ts": 0,
            "heartbeat_age_sec": None,
        }
        out.append(row)

    order = {"running": 0, "stale": 1, "stopped": 2, "unknown": 3, "untracked": 4, "terminated": 5, "local": 6}
    out.sort(key=lambda x: (order.get(x.get("derived_status") or "unknown", 99),
                            -(int(x.get("last_seen_ts") or 0))))

    return {"count": len(out), "items": out, "aws": aws}

@router.post("/nodes/register")
def nodes_register(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_operator(request)

    node_id = (req.get("node_id") or req.get("fqdn") or req.get("instance_id") or "").strip()
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

    node_id = (req.get("node_id") or req.get("fqdn") or req.get("instance_id") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="missing instance_id/node_id/fqdn")

    status = (req.get("status") or "online").strip()
    extra = {}
    for k in ("private_ip", "public_ip", "public_dns", "fqdn", "hostname"):
        if k in req:
            extra[k] = req.get(k)

    rec = touch_heartbeat(node_id, status=status, extra=extra)
    return {"ok": True, "node_id": node_id, "last_seen_ts": rec.get("last_seen_ts"), "status": rec.get("status")}



# ----------------------------
# Units: simple file-backed org tree (operator auth)
# ----------------------------
