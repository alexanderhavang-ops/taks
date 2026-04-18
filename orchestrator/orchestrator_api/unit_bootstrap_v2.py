from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from orchestrator_core.bundles import bundle_readiness
from orchestrator_core.policy_caps import describe_unit_policy
from orchestrator_core.unit_bootstrap import (
    delete_local_file,
    effective_file_texts,
    list_effective_sources,
    list_local_files,
    local_file_path,
    local_file_texts,
    write_local_file,
)

from .api_v2 import require_operator

router = APIRouter(prefix="/api/v2/units")


def _validate_unit_id(s: str) -> str:
    s = str(s or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="unit_path is required")
    if "\\" in s or s in (".", "..") or ".." in s:
        raise HTTPException(status_code=400, detail="invalid unit_path")
    return s.strip("/")


def _validate_kind(kind: str) -> bool:
    k = str(kind or "").strip().lower()
    if k in ("config", "conf", "conf.d"):
        return False
    if k in ("secret", "secrets", "secrets.d"):
        return True
    raise HTTPException(status_code=400, detail=f"invalid kind: {kind}")


def _validate_scope(scope: str) -> str:
    s = str(scope or "").strip().lower() or "local"
    if s not in ("local", "effective"):
        raise HTTPException(status_code=400, detail=f"invalid scope: {scope}")
    return s


def _parse_present_keys(text: str) -> set[str]:
    out: set[str] = set()
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, _ = line.split("=", 1)
        k = k.strip()
        if k:
            out.add(k)
    return out


def _effective_policy_id(unit_id: str) -> str:
    conf = effective_file_texts(unit_id, secret=False)
    txt = str(conf.get("policy.conf") or "")
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "default_policy_id":
            return str(v or "").strip()
    return ""


def _seed_plan_for_missing(unit_id: str, missing: List[str]) -> Dict[str, Dict[str, Dict[str, str]]]:
    missing_set = {str(x).strip() for x in (missing or []) if str(x).strip()}
    policy_id = _effective_policy_id(unit_id)

    conf_d: Dict[str, Dict[str, str]] = {}
    secrets_d: Dict[str, Dict[str, str]] = {}

    def has_conf_key(key: str) -> bool:
        return (
            f"conf.d/*:{key}" in missing_set
            or f"missing critical bootstrap config key: {key}" in missing_set
        )

    def has_secret_key(key: str) -> bool:
        return (
            f"secrets.d/*:{key}" in missing_set
            or f"missing critical bootstrap secret key: {key}" in missing_set
        )

    if has_conf_key("default_policy_id"):
        conf_d.setdefault("policy.conf", {})["default_policy_id"] = policy_id

    cert_conf_keys = [
        "cert_country",
        "cert_state",
        "cert_city",
        "cert_organization",
    ]
    cert_conf_missing = [k for k in cert_conf_keys if has_conf_key(k)]
    if cert_conf_missing:
        target = conf_d.setdefault("certs.conf", {})
        for k in cert_conf_missing:
            target[k] = "CHANGEME"

    if has_conf_key("takctl_admin_user"):
        conf_d.setdefault("takctl.conf", {})["takctl_admin_user"] = "CHANGEME"

    if has_secret_key("takctl_admin_password"):
        secrets_d.setdefault("takctl.conf", {})["takctl_admin_password"] = "CHANGEME"

    cert_secret_keys = [
        "cert_capass",
        "cert_pass",
    ]
    cert_secret_missing = [k for k in cert_secret_keys if has_secret_key(k)]
    if cert_secret_missing:
        target = secrets_d.setdefault("certs.conf", {})
        for key in cert_secret_missing:
            target[key] = "CHANGEME"

    if has_secret_key("serverpassword"):
        secrets_d.setdefault("murmur.conf", {})["serverpassword"] = "CHANGEME"

    return {
        "conf_d": conf_d,
        "secrets_d": secrets_d,
    }

def _merge_seed_content(existing: str, kv: Dict[str, str]) -> tuple[str, List[str]]:
    text = str(existing or "")
    present = _parse_present_keys(text)
    added: List[str] = []

    lines_to_add: List[str] = []
    if not text.strip():
        lines_to_add.append("# seeded by orchestrator UI")

    for key, value in kv.items():
        if key in present:
            continue
        lines_to_add.append(f"{key} = {value}")
        added.append(key)

    if not added:
        return text, added

    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n".join(lines_to_add) + "\n"
    return text, added


@router.get("/{unit_path}/bootstrap")
def get_unit_bootstrap(unit_path: str, request: Request) -> Dict[str, Any]:
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)

    local_conf = local_file_texts(unit_id, secret=False)
    local_sec = local_file_texts(unit_id, secret=True)
    eff_conf = effective_file_texts(unit_id, secret=False)
    eff_sec = effective_file_texts(unit_id, secret=True)
    eff_conf_sources = list_effective_sources(unit_id, secret=False)
    eff_sec_sources = list_effective_sources(unit_id, secret=True)

    return {
        "ok": True,
        "unit": unit_id,
        "policy": describe_unit_policy(unit_id),
        "local": {
            "conf_d": local_conf,
            "secrets_d": local_sec,
        },
        "effective": {
            "conf_d": eff_conf,
            "secrets_d": eff_sec,
        },
        "effective_sources": {
            "conf_d": eff_conf_sources,
            "secrets_d": eff_sec_sources,
        },
    }


@router.post("/{unit_path}/bootstrap/seed-critical")
def seed_unit_bootstrap_critical(unit_path: str, request: Request, role: str = "tak-node") -> Dict[str, Any]:
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)

    readiness_before = bundle_readiness(unit_id, role)
    missing_before = [str(x).strip() for x in (readiness_before.get("missing") or []) if str(x).strip()]
    plan = _seed_plan_for_missing(unit_id, missing_before)

    out: Dict[str, Any] = {
        "ok": True,
        "unit": unit_id,
        "role": role,
        "seeded": {
            "conf_d": [],
            "secrets_d": [],
        },
        "skipped": [],
        "readiness_before": readiness_before,
    }

    handled_missing: set[str] = set()

    for kind_name, files in plan.items():
        secret = kind_name == "secrets_d"
        for name, kv in files.items():
            try:
                p = local_file_path(unit_id, secret=secret, name=name)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            existing = p.read_text(encoding="utf-8") if p.exists() and p.is_file() else ""
            merged, added_keys = _merge_seed_content(existing, kv)
            if added_keys:
                dst = write_local_file(unit_id, secret=secret, name=name, content=merged)
                out["seeded"][kind_name].append({
                    "name": name,
                    "path": str(dst),
                    "added_keys": added_keys,
                })
            else:
                out["seeded"][kind_name].append({
                    "name": name,
                    "path": str(p),
                    "added_keys": [],
                })

            for key in kv.keys():
                if kind_name == "conf_d" and key == "default_policy_id":
                    handled_missing.add("conf.d/*:default_policy_id")
                    handled_missing.add("missing critical bootstrap config key: default_policy_id")
                elif kind_name == "conf_d" and key == "takctl_admin_user":
                    handled_missing.add("conf.d/*:takctl_admin_user")
                    handled_missing.add("missing critical bootstrap config key: takctl_admin_user")
                elif kind_name == "conf_d":
                    handled_missing.add(key)
                    handled_missing.add(f"missing critical bootstrap config key: {key}")
                elif kind_name == "secrets_d" and key == "takctl_admin_password":
                    handled_missing.add("secrets.d/*:takctl_admin_password")
                    handled_missing.add("missing critical bootstrap secret key: takctl_admin_password")
                elif kind_name == "secrets_d" and key in ("cert_capass", "cert_pass"):
                    handled_missing.add(f"secrets.d/*:{key}")
                    handled_missing.add(f"missing critical bootstrap secret key: {key}")
                elif kind_name == "secrets_d" and key == "serverpassword":
                    handled_missing.add("secrets.d/*:serverpassword")
                    handled_missing.add("missing critical bootstrap secret key: serverpassword")

    for item in missing_before:
        if item not in handled_missing:
            out["skipped"].append(item)

    out["readiness_after"] = bundle_readiness(unit_id, role)
    return out


@router.get("/{unit_path}/bootstrap/files")
def list_unit_bootstrap_files(unit_path: str, request: Request) -> JSONResponse:
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)

    def build(secret: bool) -> List[Dict[str, Any]]:
        local = list_local_files(unit_id, secret=secret)
        effective = effective_file_texts(unit_id, secret=secret)
        sources = list_effective_sources(unit_id, secret=secret)
        items: List[Dict[str, Any]] = []
        for name in sorted(set(local.keys()) | set(effective.keys())):
            items.append({
                "name": name,
                "kind": "secrets.d" if secret else "conf.d",
                "local": name in local,
                "effective": name in effective,
                "sources": sources.get(name, []),
                "bytes": len(effective.get(name, local.get(name).read_text(encoding="utf-8") if name in local else "")),
            })
        return items

    return JSONResponse({
        "ok": True,
        "unit": unit_id,
        "conf_d": build(secret=False),
        "secrets_d": build(secret=True),
    })


@router.get("/{unit_path}/bootstrap/file")
def get_unit_bootstrap_file(unit_path: str, kind: str, name: str, scope: str = "local", request: Request = None):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)
    scope = _validate_scope(scope)

    if scope == "local":
        try:
            p = local_file_path(unit_id, secret=secret, name=name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="local file not found")
        return PlainTextResponse(p.read_text(encoding="utf-8"))

    text_map = effective_file_texts(unit_id, secret=secret)
    if name not in text_map:
        raise HTTPException(status_code=404, detail="effective file not found")
    return PlainTextResponse(text_map[name])


@router.post("/{unit_path}/bootstrap/file")
async def save_unit_bootstrap_file(unit_path: str, kind: str, name: str, request: Request):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)

    try:
        body = await request.json()
        content = str((body or {}).get("content") or "")
    except Exception:
        content = (await request.body()).decode("utf-8", errors="replace")

    try:
        p = write_local_file(unit_id, secret=secret, name=name, content=content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ok": True,
        "unit": unit_id,
        "kind": "secrets.d" if secret else "conf.d",
        "name": name,
        "path": str(p),
    }


@router.delete("/{unit_path}/bootstrap/file")
def delete_unit_bootstrap_file(unit_path: str, kind: str, name: str, request: Request):
    require_operator(request)
    unit_id = _validate_unit_id(unit_path)
    secret = _validate_kind(kind)
    try:
        p = delete_local_file(unit_id, secret=secret, name=name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="local file not found")

    return {
        "ok": True,
        "unit": unit_id,
        "kind": "secrets.d" if secret else "conf.d",
        "name": name,
        "path": str(p),
    }
