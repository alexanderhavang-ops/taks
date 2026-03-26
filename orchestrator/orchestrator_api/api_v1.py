# orchestrator/orchestrator_api/api_v1.py
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .authz import require_auth
from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.nodes_state import upsert_node, touch_heartbeat, list_nodes
from orchestrator_core.bundles import rendered_bundles_dir, build_bundle_from_state
from orchestrator_core.core import aws_list_nodes

router = APIRouter(prefix="/api/v1")


# ----------------------------
# Bundles: signed-url helpers
# ----------------------------
def _bundle_dir() -> Path:
    return rendered_bundles_dir()


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ts_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _bundle_secret() -> str:
    secrets = load_secrets_config()
    s = str(secrets.auth.session_secret).strip()
    if s:
        return s
    raise RuntimeError("Missing auth.session_secret in /etc/taks/secrets.conf")


def _resolve_bundle_path(bundle_name: str) -> Path:
    d = _bundle_dir()
    d.mkdir(parents=True, exist_ok=True)

    p = d / bundle_name
    if p.exists():
        return p

    pzip = d / f"{bundle_name}.zip"
    ptgz = d / f"{bundle_name}.tar.gz"
    if pzip.exists():
        return pzip
    if ptgz.exists():
        return ptgz

    raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_name}")


def _token_payload(name: str, exp: int, sha256_hex: str) -> bytes:
    return f"{name}|{exp}|{sha256_hex}".encode("utf-8")


def _token_sign(name: str, exp: int, sha256_hex: str) -> str:
    secret = _bundle_secret().encode("utf-8")
    payload = _token_payload(name, exp, sha256_hex)
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    import base64
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _token_verify(name: str, exp: int, sha256_hex: str, token: str) -> bool:
    if int(time.time()) > int(exp):
        return False
    want = _token_sign(name, exp, sha256_hex)
    return hmac.compare_digest(want, token)


# ----------------------------
# Request normalization (backward compatible)
# ----------------------------
def _normalize_node_req(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward compat:
      - battalion => unit_path
      - missing role => default "tak-node" (for old callers)
    """
    d = dict(req or {})
    if "unit_path" not in d and "battalion" in d:
        d["unit_path"] = str(d.pop("battalion"))
    if "role" not in d or not str(d.get("role") or "").strip():
        d["role"] = "tak-node"
    # Provide defaults for required NodeRequest fields (backward compatible)
    unit_path = str(d.get("unit_path") or "").strip()
    # hostname: stable + DNS-safe-ish
    if "hostname" not in d or not str(d.get("hostname") or "").strip():
        safe = unit_path.replace("/", "-").replace("_", "-")
        d["hostname"] = f"tak-{safe}" if safe else "tak-node"
    # name: AWS tag Name (default to hostname)
    if "name" not in d or not str(d.get("name") or "").strip():
        d["name"] = str(d.get("hostname") or "tak-node")
    # fqdn: best-effort default if caller didn't provide one
    if "fqdn" not in d or not str(d.get("fqdn") or "").strip():
        cfg = load_orch_config()
        dns_suffix = str(cfg.nodes.default_node_domain).strip().strip(".")
        if unit_path and "." in unit_path:
            d["fqdn"] = unit_path
        elif unit_path:
            d["fqdn"] = f"{unit_path}.{dns_suffix}"
        else:
            d["fqdn"] = f"{d['hostname']}.{dns_suffix}"

    return d


# ----------------------------
# Status (no auth)
# ----------------------------
@router.get("/status")
def api_status() -> Dict[str, Any]:
    out = aws_list_nodes()
    if not isinstance(out, dict):
        return {"provider": "aws", "error": "unexpected aws_list_nodes() response"}

    cfg = load_orch_config()
    secrets = load_secrets_config()

    out["launch_enabled"] = cfg.aws.launch_enabled
    out["requirements"] = {
        "aws_key_name": bool(str(cfg.aws.ssh_key_name).strip()),
        "sg_id": bool(str(cfg.aws.default_security_group_id).strip()),
        "subnet_id": bool(str(cfg.aws.default_subnet_id).strip()),
        "image_id": bool(str(cfg.aws.default_ami).strip()),
        "bundle_secret": bool(str(secrets.auth.session_secret).strip()),
    }
    out["hints"] = {
        "aws_key_name": "Set aws.ssh_key_name in /etc/taks/tak_orch.conf",
        "sg_id": "Set aws.default_security_group_id in /etc/taks/tak_orch.conf",
        "subnet_id": "Set aws.default_subnet_id in /etc/taks/tak_orch.conf",
        "image_id": "Set aws.default_ami in /etc/taks/tak_orch.conf",
        "bundle_secret": "Set auth.session_secret in /etc/taks/secrets.conf",
    }
    return out


# ----------------------------
# Bundles: build from state (auth)
# ----------------------------
@router.post("/bundles/build")
def bundles_build(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Build a bundle tarball from orchestrator state overlays:
      roles/<role>/bundle/ + units/<unit_path>/bundle/

    Request:
      { "unit_path": "...", "role": "...", "bundle_name": "optional.tar.gz" }
    """
    require_auth(request)
    unit_path = str(req.get("unit_path") or req.get("battalion") or "").strip()
    role = str(req.get("role") or "tak-node").strip()
    bundle_name = (req.get("bundle_name") or None)
    if not unit_path:
        raise HTTPException(status_code=400, detail="Missing unit_path")

    try:
        r = build_bundle_from_state(unit_path=unit_path, role=role, bundle_name=bundle_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "bundle_name": r.get("bundle_name"),
        "tar_path": str(r.get("tar_path") or ""),
        "manifest_path": str(r.get("manifest_path") or ""),
        "overlays": r.get("overlays") or [],
    }


# ----------------------------
# Nodes (auth)
# ----------------------------




@router.get("/nodes")
def nodes_list(request: Request) -> Dict[str, Any]:
    require_auth(request)
    items = list_nodes()
    return {"count": len(items), "items": items}


@router.get("/nodes/{node_id}")
def nodes_get(node_id: str, request: Request) -> Dict[str, Any]:
    require_auth(request)
    items = [x for x in list_nodes() if str(x.get("node_id")) == node_id]
    if not items:
        raise HTTPException(status_code=404, detail="node not found")
    return items[0]


@router.post("/nodes/register")
def nodes_register(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Node -> orchestrator registration (push).
    Node authenticates with BASIC using the orch_api_user/pass embedded in cloud-init.
    """
    require_auth(request)

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
    """
    Node heartbeat.
    """
    require_auth(request)
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


# ----------------------------
# Bundles (list + signed-url + download)
# ----------------------------
@router.get("/bundles")
def bundles_list(request: Request) -> Dict[str, Any]:
    require_auth(request)

    d = _bundle_dir()
    d.mkdir(parents=True, exist_ok=True)

    items = []
    for p in sorted(d.glob("*")):
        if not p.is_file():
            continue
        if not (p.name.endswith(".zip") or p.name.endswith(".tar.gz") or p.name.endswith(".manifest.json")):
            continue

        st = p.stat()
        items.append(
            {
                "name": p.name,
                "size": st.st_size,
                "mtime": _ts_iso(st.st_mtime),
                "sha256": _sha256_file(p) if (p.name.endswith(".zip") or p.name.endswith(".tar.gz")) else None,
            }
        )

    return {"bundle_dir": str(d), "count": len(items), "items": items}


@router.get("/bundles/{bundle_name}")
def bundle_manifest(bundle_name: str, request: Request) -> Dict[str, Any]:
    require_auth(request)

    d = _bundle_dir()
    d.mkdir(parents=True, exist_ok=True)

    base = bundle_name
    if base.endswith(".zip"):
        base = base[: -len(".zip")]
    if base.endswith(".tar.gz"):
        base = base[: -len(".tar.gz")]

    m = d / f"{base}.manifest.json"
    if not m.exists():
        raise HTTPException(status_code=404, detail=f"Manifest not found: {m.name}")

    try:
        data = json.loads(m.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid manifest JSON: {e}")

    return {"name": m.name, "manifest": data}



@router.api_route("/bundles/{bundle_name}/download", methods=["GET", "HEAD"], operation_id="bundle_download_v1")
def bundle_download(bundle_name: str, request: Request, exp: Optional[int] = None, token: Optional[str] = None):
    # Signed URL path (no BASIC)
    if exp is not None and token is not None:
        p = _resolve_bundle_path(bundle_name)
        sha = _sha256_file(p)
        if not _token_verify(p.name, int(exp), sha, token):
            raise HTTPException(status_code=401, detail="Invalid or expired signed URL")
        return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")

    # Otherwise require auth (cookie or BASIC).
    require_auth(request)
    p = _resolve_bundle_path(bundle_name)
    return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")

