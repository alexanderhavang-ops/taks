# orchestrator/orchestrator_api/api_v1.py
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

\1from orchestrator_core.nodes_state import upsert_node, touch_heartbeat, list_nodes
from orchestrator_core.core import NodeRequest, plan_node, aws_dry_run, aws_launch, aws_list_nodes

router = APIRouter(prefix="/api/v1")


# ----------------------------
# Auth (BASIC) for operator actions
# ----------------------------
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


def require_basic(request: Request) -> None:
    if not _basic_auth_ok(request):
        raise HTTPException(status_code=401, detail="Unauthorized (BASIC auth required)")


# ----------------------------
# Bundles: signed-url helpers
# ----------------------------
def _bundle_dir() -> Path:
    return Path(os.environ.get("TAKS_BUNDLE_DIR") or "/opt/tak-orch/state/bundles")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ts_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _bundle_secret() -> str:
    s = (os.environ.get("TAKS_BUNDLE_SECRET") or "").strip()
    if s:
        return s
    s2 = (os.environ.get("TAKS_UI_SECRET") or "").strip()
    if s2:
        return s2
    raise RuntimeError("Missing TAKS_BUNDLE_SECRET (or fallback TAKS_UI_SECRET)")


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
        base = os.environ.get("TAKS_DEFAULT_NODE_DOMAIN") or "tak-hv-sandbox.se"
        # If unit_path already looks like a hostname, keep it; else use <unit_path>.<base>
        if unit_path and "." in unit_path:
            d["fqdn"] = unit_path
        elif unit_path:
            d["fqdn"] = f"{unit_path}.{base}"
        else:
            d["fqdn"] = f"{d['hostname']}.{base}"

    return d


# ----------------------------
# Status (no auth)
# ----------------------------
@router.get("/status")
def api_status() -> Dict[str, Any]:
    out = aws_list_nodes()
    if not isinstance(out, dict):
        return {"provider": "aws", "error": "unexpected aws_list_nodes() response"}

    launch_enabled = (os.environ.get("TAKS_LAUNCH_ENABLED") == "1")
    out["launch_enabled"] = launch_enabled

    out["requirements"] = {
        "aws_key_name": bool(os.environ.get("TAKS_AWS_KEY_NAME")),
        "sg_id": bool(os.environ.get("TAKS_AWS_SG_ID")),
        "subnet_id": bool(os.environ.get("TAKS_SUBNET_ID")),
        "image_id": bool(os.environ.get("TAKS_IMAGE_ID")),
        "bundle_secret": bool((os.environ.get("TAKS_BUNDLE_SECRET") or os.environ.get("TAKS_UI_SECRET") or "").strip()),
    }
    out["hints"] = {
        "aws_key_name": "Set env TAKS_AWS_KEY_NAME (EC2 keypair name) or pass aws_key_name in /nodes/launch request",
        "sg_id": "Set env TAKS_AWS_SG_ID to a security group *ID* (sg-...) in the same VPC/subnet",
        "subnet_id": "Optionally set env TAKS_SUBNET_ID (subnet-...)",
        "image_id": "Optionally set env TAKS_IMAGE_ID (ami-...)",
        "bundle_secret": "Set env TAKS_BUNDLE_SECRET (preferred) or fallback TAKS_UI_SECRET to enable signed bundle URLs",
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
    require_basic(request)
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
        "bundle_name": r.bundle_name,
        "tar_path": str(r.tar_path),
        "manifest_path": str(r.manifest_path),
        "overlays": r.overlays,
    }


# ----------------------------
# Nodes (auth)
# ----------------------------
@router.post("/nodes/preview")
def nodes_preview(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_basic(request)
    nr = NodeRequest(**_normalize_node_req(req))
    return plan_node(nr)


@router.post("/nodes/dry-run")
def nodes_dry_run(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_basic(request)
    nr = NodeRequest(**_normalize_node_req(req))
    return aws_dry_run(nr)


@router.post("/nodes/cloud-init")
def nodes_cloud_init(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Render the exact cloud-init we would send to EC2, including signed bundle URL if bundle_name is provided.
    This is verification-only (no AWS calls).
    """
    require_basic(request)
    nr = NodeRequest(**_normalize_node_req(req))

    # Auto-build bundle if requested and missing
    if nr.bundle_name:
        want = nr.bundle_name
        if want and not (want.endswith(".tar.gz") or want.endswith(".zip")):
            want = want + ".tar.gz"
        p_try = bundles_dir() / want
        if p_try.exists():
            nr.bundle_name = want
        else:
            built = build_bundle_from_state(unit_path=nr.unit_path, role=nr.role, bundle_name=want)
            nr.bundle_name = built.bundle_name

        # Mint signed bundle URL and inject into cloud-init via nr.bundle_url
        p = _resolve_bundle_path(nr.bundle_name)
        sha = _sha256_file(p)

        ttl = int(nr.bundle_ttl or 3600)
        if ttl < 60:
            ttl = 60
        if ttl > 7 * 24 * 3600:
            ttl = 7 * 24 * 3600

        exp = int(time.time()) + ttl
        token = _token_sign(p.name, exp, sha)
        dl = request.url_for("bundle_download", bundle_name=p.name)
        nr.bundle_url = f"{dl}?exp={exp}&token={token}"
        nr.bundle_sha256 = sha

    plan = plan_node(nr)
    return {
        "bundle_url": nr.bundle_url,
        "cloud_init": plan.get("cloud_init", ""),
        "plan": {k: plan[k] for k in ("region", "ami", "vpc_id", "subnet_id", "instance_type", "tags") if k in plan},
    }


@router.post("/nodes/launch")
def nodes_launch(req: Dict[str, Any], request: Request) -> Dict[str, Any]:
    require_basic(request)
    nr = NodeRequest(**_normalize_node_req(req))

    if os.environ.get("TAKS_LAUNCH_ENABLED") != "1":
        raise HTTPException(status_code=400, detail="Launch disabled (set TAKS_LAUNCH_ENABLED=1)")

    # Auto-build bundle if requested and missing, then mint signed URL
    if nr.bundle_name:
        p_try = bundles_dir() / nr.bundle_name
        if not p_try.exists():
            built = build_bundle_from_state(unit_path=nr.unit_path, role=nr.role, bundle_name=nr.bundle_name)
            nr.bundle_name = built.bundle_name

        p = _resolve_bundle_path(nr.bundle_name)
        sha = _sha256_file(p)

        ttl = int(nr.bundle_ttl or 3600)
        if ttl < 60:
            ttl = 60
        if ttl > 7 * 24 * 3600:
            ttl = 7 * 24 * 3600

        exp = int(time.time()) + ttl
        token = _token_sign(p.name, exp, sha)
        dl = request.url_for("bundle_download", bundle_name=p.name)
        nr.bundle_url = f"{dl}?exp={exp}&token={token}"
        nr.bundle_sha256 = sha

    return aws_launch(nr)


# ----------------------------
# Node state (auth)
# ----------------------------
@router.get("/nodes")
def nodes_list(request: Request) -> Dict[str, Any]:
    require_basic(request)
    items = list_nodes()
    return {"count": len(items), "items": items}


@router.get("/nodes/{node_id}")
def nodes_get(node_id: str, request: Request) -> Dict[str, Any]:
    require_basic(request)
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
    require_basic(request)

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
    require_basic(request)
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
    require_basic(request)

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
    require_basic(request)

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


@router.get("/bundles/{bundle_name}/signed-url")
def bundle_signed_url(bundle_name: str, request: Request, ttl: int = 3600) -> Dict[str, Any]:
    require_basic(request)

    p = _resolve_bundle_path(bundle_name)
    sha = _sha256_file(p)

    ttl = int(ttl)
    if ttl < 60:
        ttl = 60
    if ttl > 7 * 24 * 3600:
        ttl = 7 * 24 * 3600

    exp = int(time.time()) + ttl
    token = _token_sign(p.name, exp, sha)
    dl = request.url_for("bundle_download", bundle_name=p.name)
    url = f"{dl}?exp={exp}&token={token}"

    return {"name": p.name, "exp": exp, "token": token, "sha256": sha, "url": url}


@router.api_route("/bundles/{bundle_name}/download", methods=["GET", "HEAD"])
def bundle_download(bundle_name: str, request: Request, exp: Optional[int] = None, token: Optional[str] = None):
    # Signed URL path (no BASIC)
    if exp is not None and token is not None:
        p = _resolve_bundle_path(bundle_name)
        sha = _sha256_file(p)
        if not _token_verify(p.name, int(exp), sha, token):
            raise HTTPException(status_code=401, detail="Invalid or expired signed URL")
        return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")

    # Otherwise require BASIC auth.
    require_basic(request)
    p = _resolve_bundle_path(bundle_name)
    return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")
