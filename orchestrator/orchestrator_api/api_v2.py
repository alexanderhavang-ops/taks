# orchestrator/orchestrator_api/api_v2.py
from __future__ import annotations

import base64
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.core import NodeRequest, aws_dry_run, aws_launch, aws_list_nodes, aws_terminate, plan_node
from orchestrator_core.nodes_state import delete_node, get_node, list_nodes, touch_heartbeat, upsert_node
from orchestrator_core.units_state import list_units, create_unit

from .auth import verify_token, verify_basic_auth
from .bundles_v2 import bundle_name_for_unit, bundle_dir, ensure_unit_bundle

router = APIRouter(prefix="/api/v2")





# ----------------------------
# Auth: allow either UI session cookie OR BASIC (for nodes)
# ----------------------------
def _cookie_auth_ok(request: Request) -> bool:
    secret = load_secrets_config().auth.session_secret.strip()
    if not secret:
        return False
    tok = request.cookies.get("taks_auth") or ""
    return bool(tok and verify_token(tok, secret))


def _basic_auth_ok(request: Request) -> bool:
    secrets = load_secrets_config()
    want_user = secrets.auth.operator_user.strip()
    want_pass = secrets.auth.operator_password.strip()

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
        fqdn_guess = str(d.get("fqdn") or "").strip()
        if fqdn_guess and "." in fqdn_guess:
            d["hostname"] = fqdn_guess.split(".", 1)[0].strip()
        else:
            safe = unit_path.replace("/", "-").replace("_", "-")
            d["hostname"] = f"tak-{safe}" if safe else "tak-node"

    if not str(d.get("name") or "").strip():
        d["name"] = str(d.get("hostname") or "tak-node")

    if not str(d.get("fqdn") or "").strip():
        cfg = load_orch_config()
        dns_suffix = str(cfg.nodes.default_node_domain).strip().strip(".")
        if unit_path and "." in unit_path:
            d["fqdn"] = unit_path
        else:
            d["fqdn"] = f"{unit_path}.{dns_suffix}"

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

    cfg = load_orch_config()
    out["launch_enabled"] = cfg.aws.launch_enabled
    out["bundle_dir"] = str(bundle_dir())
    out["launch_defaults"] = {
        "region": cfg.aws.region,
        "ami": cfg.aws.default_ami,
        "subnet_id": cfg.aws.default_subnet_id,
        "security_group_id": cfg.aws.default_security_group_id,
        "instance_profile": cfg.aws.default_instance_profile,
        "instance_type": cfg.aws.default_instance_type,
        "ssh_key_name": cfg.aws.ssh_key_name,
        "default_node_domain": cfg.nodes.default_node_domain,
    }
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
    if not load_orch_config().aws.launch_enabled:
        raise HTTPException(status_code=400, detail="Launch disabled by config (aws.launch_enabled=false)")
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
        "aws_instance_id": instance_id,
        "unit_path": nr.unit_path,
        "role": nr.role,
        "fqdn": nr.fqdn,
        "hostname": nr.hostname,
        "region": launch.get("region"),
        "status": "booting",
        "aws_state": launch.get("state"),
        "private_ip": launch.get("private_ip"),
        "public_ip": launch.get("public_ip"),
        "aws_private_ip": launch.get("private_ip"),
        "aws_public_ip": launch.get("public_ip"),
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

    aws = aws_list_nodes()
    aws_instances = list((aws or {}).get("instances") or [])

    want_node_id = str(rec.get("node_id") or node_id or "").strip()
    want_fqdn = str(rec.get("fqdn") or "").strip()
    want_priv = str(rec.get("private_ip") or rec.get("aws_private_ip") or "").strip()
    want_pub = str(rec.get("public_ip") or rec.get("aws_public_ip") or "").strip()
    want_iid = str(rec.get("aws_instance_id") or rec.get("instance_id") or "").strip()

    matched = None

    for inst in aws_instances:
        iid = str(inst.get("instance_id") or "").strip()
        fqdn = str(inst.get("fqdn") or "").strip()
        priv = str(inst.get("private_ip") or "").strip()
        pub = str(inst.get("public_ip") or "").strip()

        if want_iid and iid and iid == want_iid:
            matched = inst
            break
        if want_priv and priv and priv == want_priv:
            matched = inst
            break
        if want_pub and pub and pub == want_pub:
            matched = inst
            break
        if want_fqdn and fqdn and fqdn == want_fqdn:
            matched = inst
            break
        if want_node_id and fqdn and fqdn == want_node_id:
            matched = inst
            break

    instance_id = str(
        ((matched or {}).get("instance_id") or want_iid or "")
    ).strip()
    if not instance_id:
        raise HTTPException(status_code=400, detail=f"node has no instance_id: {node_id}")

    term = aws_terminate(instance_id)

    patch = {
        "node_id": rec.get("node_id") or node_id,
        "instance_id": instance_id,
        "aws_instance_id": instance_id,
        "status": "terminating",
        "aws_state": term.get("current_state") or "terminating",
    }
    updated = upsert_node(str(rec.get("node_id") or node_id), patch)
    return {"ok": True, "terminate": term, "node": updated}



@router.delete("/nodes/{node_id}")
def nodes_delete(node_id: str, request: Request) -> Dict[str, Any]:
    require_operator(request)
    ok = delete_node(node_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"node not found: {node_id}")
    return {"ok": True, "node_id": node_id}


@router.get("/nodes")
def nodes_list(request: Request) -> Dict[str, Any]:
    require_operator(request)

    state_items = list_nodes()
    aws = aws_list_nodes()
    aws_instances = list(aws.get("instances") or [])

    now = int(time.time())

    active = []
    orphaned = []
    untracked = []

    aws_by_id = {}
    aws_by_pub = {}
    aws_by_priv = {}

    for inst in aws_instances:
        iid = str(inst.get("instance_id") or "").strip()
        pub = str(inst.get("public_ip") or "").strip()
        priv = str(inst.get("private_ip") or "").strip()

        if iid:
            aws_by_id[iid] = inst
        if pub:
            aws_by_pub[pub] = inst
        if priv:
            aws_by_priv[priv] = inst

    matched_aws_ids = set()

    for n in state_items:
        row = dict(n)

        node_id = str(row.get("node_id") or "").strip()
        inst_id = str(row.get("instance_id") or "").strip()
        pub = str(row.get("public_ip") or "").strip()
        priv = str(row.get("private_ip") or "").strip()
        last_seen = int(row.get("last_seen_ts") or 0)
        heartbeat_age = (now - last_seen) if last_seen else None


        aws_rec = None
        if inst_id and inst_id in aws_by_id:
            aws_rec = aws_by_id[inst_id]
        elif pub and pub in aws_by_pub:
            aws_rec = aws_by_pub[pub]
        elif priv and priv in aws_by_priv:
            aws_rec = aws_by_priv[priv]

        if aws_rec is None:
            row["aws_state"] = "missing"
            row["heartbeat_age_sec"] = heartbeat_age
            row["derived_status"] = "orphaned"
            orphaned.append(row)
            continue

        aws_state = str(aws_rec.get("state") or "unknown").strip().lower()
        aws_iid = str(aws_rec.get("instance_id") or "").strip()
        if aws_iid:
            matched_aws_ids.add(aws_iid)

        row["aws_state"] = aws_state
        row["heartbeat_age_sec"] = heartbeat_age
        row["derived_status"] = "active"

        row["aws_instance_id"] = aws_rec.get("instance_id")
        row["aws_private_ip"] = aws_rec.get("private_ip")
        row["aws_public_ip"] = aws_rec.get("public_ip")
        row["availability_zone"] = aws_rec.get("availability_zone")
        row["instance_type"] = aws_rec.get("instance_type") or ((row.get("meta") or {}).get("instance_type"))
        row["subnet_id"] = aws_rec.get("subnet_id") or ((row.get("meta") or {}).get("subnet_id"))
        row["vpc_id"] = aws_rec.get("vpc_id")
        row["image_id"] = aws_rec.get("image_id")
        row["launch_time"] = aws_rec.get("launch_time")
        row["iam_instance_profile_arn"] = aws_rec.get("iam_instance_profile_arn")
        row["security_groups"] = aws_rec.get("security_groups") or []
        row["aws_tags"] = aws_rec.get("tags") or {}
        row["display_name"] = str(((row.get("meta") or {}).get("name")) or row.get("hostname") or row.get("fqdn") or row.get("node_id") or "").strip()

        if aws_rec.get("instance_id"):
            row["instance_id"] = aws_rec.get("instance_id")
        if aws_rec.get("public_ip"):
            row["public_ip"] = aws_rec.get("public_ip")
        if aws_rec.get("private_ip"):
            row["private_ip"] = aws_rec.get("private_ip")
        if aws_rec.get("public_dns"):
            row["public_dns"] = aws_rec.get("public_dns")

        active.append(row)

    cfg = load_orch_config()
    fqdn_suffix = str(cfg.nodes.default_node_domain).strip().strip(".")

    for aws_rec in aws_instances:
        inst_id = str(aws_rec.get("instance_id") or "").strip()
        if not inst_id or inst_id in matched_aws_ids:
            continue

        unit_path = str(aws_rec.get("unit_path") or "").strip()
        fqdn = ""
        if unit_path and "." in unit_path:
            fqdn = unit_path
        elif unit_path and fqdn_suffix:
            fqdn = f"{unit_path}.{fqdn_suffix}"

        row = {
            "node_id": inst_id,
            "instance_id": inst_id,
            "unit_path": unit_path,
            "role": aws_rec.get("role") or "",
            "fqdn": fqdn,
            "hostname": aws_rec.get("name") or "",
            "display_name": aws_rec.get("name") or unit_path or inst_id,
            "public_dns": aws_rec.get("public_dns") or "",
            "public_ip": aws_rec.get("public_ip") or "",
            "private_ip": aws_rec.get("private_ip") or "",
            "aws_state": str(aws_rec.get("state") or "unknown").strip().lower(),
            "derived_status": "untracked",
            "last_seen_ts": 0,
            "heartbeat_age_sec": None,
            "aws_instance_id": aws_rec.get("instance_id") or "",
            "aws_public_ip": aws_rec.get("public_ip") or "",
            "aws_private_ip": aws_rec.get("private_ip") or "",
            "region": aws_rec.get("region"),
            "availability_zone": aws_rec.get("availability_zone"),
            "instance_type": aws_rec.get("instance_type"),
            "subnet_id": aws_rec.get("subnet_id"),
            "vpc_id": aws_rec.get("vpc_id"),
            "image_id": aws_rec.get("image_id"),
            "launch_time": aws_rec.get("launch_time"),
            "iam_instance_profile_arn": aws_rec.get("iam_instance_profile_arn"),
            "security_groups": aws_rec.get("security_groups") or [],
            "aws_tags": aws_rec.get("tags") or {},
        }
        untracked.append(row)

    active.sort(key=lambda x: -(int(x.get("last_seen_ts") or 0)))
    untracked.sort(key=lambda x: str(x.get("instance_id") or ""))
    orphaned.sort(key=lambda x: -(int(x.get("last_seen_ts") or 0)))

    return {
        "count": len(active),
        "items": active,
        "untracked_items": untracked,
        "orphaned_items": orphaned,
        "aws": aws,
    }

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
    if not verify_basic_auth(request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="Unauthorized (node BASIC auth required)")

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
