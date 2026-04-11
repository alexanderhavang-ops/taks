from __future__ import annotations

import json
import os
import tarfile
import shutil
from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.unit_bootstrap import effective_bootstrap_for_bundle
from orchestrator_core.branding_resolver import materialize_branding_bundle
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")

REPO_EXCLUDE_NAMES = {
    ".git",
    ".github",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "bundles",
    "rendered",
    "artifacts",
}
REPO_EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".swp",
    ".tmp",
    ".tar.gz",
    ".zip",
}


def _state_dir() -> Path:
    cfg = load_orch_config()
    return Path(cfg.paths.state_dir)


def bundles_dir() -> Path:
    cfg = load_orch_config()
    d = Path(cfg.paths.rendered_bundles_dir).parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def rendered_bundles_dir() -> Path:
    cfg = load_orch_config()
    d = Path(cfg.paths.rendered_bundles_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def units_dir() -> Path:
    d = _state_dir() / "units"
    d.mkdir(parents=True, exist_ok=True)
    return d


def roles_dir() -> Path:
    d = _state_dir() / "roles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_bundle_dir() -> Path:
    return Path(__file__).resolve().parent / "default_bundle"


def _looks_like_taks_repo(p: Path) -> bool:
    return (
        p.is_dir()
        and (p / "orchestrator").is_dir()
        and (p / "tak-installer").is_dir()
        and (p / "takctl").is_dir()
    )


def repo_root_dir() -> Path:
    cfg = load_orch_config()
    root = Path(cfg.bundles.source_repo_root)
    if not _looks_like_taks_repo(root):
        raise RuntimeError(f"configured TAKS repo root is invalid: {root}")
    return root


def _safe_unit_fs(unit_path: str) -> str:
    up = (unit_path or "").strip().strip("/")
    if not up:
        raise ValueError("unit_path must be non-empty")
    return up


def _unit_dir(unit_path: str) -> Path:
    return units_dir() / _safe_unit_fs(unit_path)


def _unit_json_path(unit_path: str) -> Path:
    return _unit_dir(unit_path) / "unit.json"


def unit_bundle_overlay_dir(unit_path: str) -> Path:
    return _unit_dir(unit_path) / "bundle"


def role_bundle_overlay_dir(role: str) -> Path:
    r = (role or "").strip()
    if not r:
        raise ValueError("role must be non-empty")
    return roles_dir() / r / "bundle"


def unit_files_root(unit_path: str) -> Path:
    return _unit_dir(unit_path) / "files"


def _meta_get(meta: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = meta.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _read_unit_json(unit_path: str) -> Dict[str, Any]:
    p = _unit_json_path(unit_path)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _read_unit_meta(unit_path: str) -> Dict[str, Any]:
    raw = _read_unit_json(unit_path)
    meta = raw.get("meta")
    return meta if isinstance(meta, dict) else {}


def _read_unit_chain(unit_path: str) -> List[str]:
    chain: List[str] = []
    cur = unit_path
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        raw = _read_unit_json(cur)
        parent = str(raw.get("parent_path") or "").strip()
        if not parent:
            break
        cur = parent
    chain.reverse()
    return chain


def _default_node_fqdn(unit_path: str, unit_meta: Dict[str, Any]) -> str:
    meta = unit_meta if isinstance(unit_meta, dict) else {}
    explicit = _meta_get(meta, "fqdn")
    if explicit:
        return explicit
    cfg = load_orch_config()
    dns_suffix = str(cfg.nodes.default_node_domain).strip().strip(".")
    safe = str(unit_path or "").strip().strip(".")
    if "." in safe:
        return safe
    return f"{safe}.{dns_suffix}" if dns_suffix else safe


def _default_node_cert_model(unit_meta: Dict[str, Any]) -> str:
    meta = unit_meta if isinstance(unit_meta, dict) else {}
    explicit = _meta_get(meta, "node_cert_model", "taks_node_cert_model", "cert_model")
    if explicit:
        return explicit
    cfg = load_orch_config()
    return str(cfg.nodes.default_cert_model).strip()




def _unit_cert_ou(unit_path: str) -> str:
    safe = _safe_unit_fs(unit_path)
    return safe.split("/")[-1].strip() or safe


def _parse_simple_conf(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[str(k).strip()] = str(v).strip()
    return out


def _render_simple_conf(rows: Dict[str, str]) -> str:
    keys = sorted(rows.keys())
    return "".join(f"{k} = {rows[k]}\n" for k in keys if str(rows[k]).strip() != "")


def _bundle_has_takserver_deb(unit_path: str, role: str) -> bool:
    pats = ("takserver_*_all.deb",)

    roots = [
        default_bundle_dir() / "packages",
        role_bundle_overlay_dir(role) / "packages",
        unit_bundle_overlay_dir(unit_path) / "packages",
        unit_files_root(unit_path) / "packages",
    ]

    for root in roots:
        if not root.exists():
            continue
        for pat in pats:
            if any(root.glob(pat)):
                return True
    return False


def _flatten_component_values(items: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _name, obj in sorted((items or {}).items()):
        if isinstance(obj, dict):
            for k, v in obj.items():
                out[str(k).strip()] = str(v).strip()
        else:
            out.update(_parse_simple_conf(str(obj)))
    return out


def bundle_readiness(unit_path: str, role: str) -> Dict[str, Any]:
    data = effective_bootstrap_for_bundle(unit_path)
    conf_d = (data.get("conf_d") or {}) if isinstance(data, dict) else {}
    secrets_d = (data.get("secrets_d") or {}) if isinstance(data, dict) else {}

    conf_vals = _flatten_component_values(conf_d)
    sec_vals = _flatten_component_values(secrets_d)

    required_cert_keys = (
        "cert_country",
        "cert_state",
        "cert_city",
        "cert_organization",
    )
    missing_cert = [k for k in required_cert_keys if not str(conf_vals.get(k) or "").strip()]

    required_bootstrap = [
        ("conf.d/*:default_policy_id", str(conf_vals.get("default_policy_id") or "").strip()),
        ("conf.d/*:takctl_admin_user", str(conf_vals.get("takctl_admin_user") or "").strip()),
        ("secrets.d/*:takctl_admin_password", str(sec_vals.get("takctl_admin_password") or "").strip()),
        ("secrets.d/*:cert_capass", str(sec_vals.get("cert_capass") or "").strip()),
        ("secrets.d/*:cert_pass", str(sec_vals.get("cert_pass") or "").strip()),
        ("secrets.d/*:serverpassword", str(sec_vals.get("serverpassword") or "").strip()),
    ]

    missing: List[str] = []
    if not _bundle_has_takserver_deb(unit_path, role):
        missing.append("takserver_deb")
    missing.extend(missing_cert)
    missing.extend([name for name, value in required_bootstrap if not value])

    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "derived": {
            "cert_organizational_unit": _unit_cert_ou(unit_path),
        },
    }
def _default_le_email(unit_meta: Dict[str, Any]) -> str:
    meta = unit_meta if isinstance(unit_meta, dict) else {}
    explicit = _meta_get(meta, "le_email", "letsencrypt_email")
    if explicit:
        return explicit
    return ""


def _write_unit_config(root: Path, *, unit_path: str, role: str) -> Path:
    unit_meta = _read_unit_json(unit_path)
    chain = _read_unit_chain(unit_path)

    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "unit_id": unit_path,
        "role": role,
        "parent_chain": chain,
        "title": str(unit_meta.get("title") or ""),
        "symbol": str(unit_meta.get("symbol") or ""),
        "slogan": str(unit_meta.get("slogan") or ""),
        "logo": str(unit_meta.get("logo") or ""),
        "meta": unit_meta.get("meta") or {},
    }

    out = config_dir / "unit.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _write_node_env(root: Path, *, unit_path: str) -> Dict[str, Any]:
    unit_meta = _read_unit_meta(unit_path)
    fqdn = _default_node_fqdn(unit_path, unit_meta)
    cert_model = _default_node_cert_model(unit_meta)
    le_email = _default_le_email(unit_meta)

    cfg = load_orch_config()
    secrets = load_secrets_config()

    conf_dir = root / "install" / "taks-bootstrap" / "config.d"
    sec_dir = root / "install" / "taks-bootstrap" / "secrets.d"
    conf_dir.mkdir(parents=True, exist_ok=True)
    sec_dir.mkdir(parents=True, exist_ok=True)

    orch_base = str(cfg.identity.public_base_url).strip().rstrip("/")
    orch_api_url = orch_base if orch_base else ""

    node_conf = {
        "fqdn": fqdn,
        "node_cert_model": cert_model,
    }
    if le_email:
        node_conf["le_email"] = le_email
    if orch_api_url:
        node_conf["orch_api_url"] = orch_api_url

    node_sec = {
        "node_api_user": str(secrets.auth.node_api_user),
        "node_api_password": str(secrets.auth.node_api_password),
    }

    conf_path = conf_dir / "node.conf"
    sec_path = sec_dir / "node_api.conf"

    conf_path.write_text(_render_simple_conf(node_conf), encoding="utf-8")
    sec_path.write_text(_render_simple_conf(node_sec), encoding="utf-8")

    return {
        "generated": "install/taks-bootstrap/{config.d/node.conf,secrets.d/node_api.conf}",
        "kind": "generated_bootstrap",
        "files": 2,
        "bytes": conf_path.stat().st_size + sec_path.stat().st_size,
    }


def _copy_wildcard_tls_material(root: Path) -> Dict[str, Any]:
    cfg = load_orch_config()
    cert_domain = str(cfg.letsencrypt.wildcard_zone).strip().strip(".")
    if not cert_domain:
        raise ValueError("letsencrypt.wildcard_zone is required for WILDCARD_DNS_01 bundle mode")

    src_dir = Path(cfg.letsencrypt.artifact_cert_dir)
    src_cert = src_dir / "fullchain.pem"
    src_key = src_dir / "privkey.pem"

    if not src_cert.is_file():
        raise ValueError(f"wildcard artifact cert missing: {src_cert}")
    if not src_key.is_file():
        raise ValueError(f"wildcard artifact key missing: {src_key}")

    dst_dir = root / "install" / "letsencrypt"
    dst_dir.mkdir(parents=True, exist_ok=True)

    dst_cert = dst_dir / "fullchain.pem"
    dst_key = dst_dir / "privkey.pem"

    dst_cert.write_bytes(src_cert.read_bytes())
    dst_key.write_bytes(src_key.read_bytes())

    return {
        "kind": "wildcard_tls_material",
        "src_cert": str(src_cert),
        "src_key": str(src_key),
        "dst_cert": "install/letsencrypt/fullchain.pem",
        "dst_key": "install/letsencrypt/privkey.pem",
        "files": 2,
        "bytes": dst_cert.stat().st_size + dst_key.stat().st_size,
    }


def _copy_tree(src: Path, dst: Path) -> Dict[str, Any]:
    files = 0
    bytes_total = 0
    exists = src.exists()

    if not exists:
        return {"src": str(src), "files": 0, "bytes": 0, "exists": False}

    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        out = dst / rel
        if p.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if p.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(p.read_bytes())
            files += 1
            bytes_total += p.stat().st_size

    return {"src": str(src), "files": files, "bytes": bytes_total, "exists": True}




def _write_effective_bootstrap(root: Path, *, unit_path: str) -> Dict[str, Any]:
    data = effective_bootstrap_for_bundle(unit_path)
    eff = ((data or {}).get("effective") or {})
    conf_d = (eff.get("conf_d") or {}) if isinstance(eff, dict) else {}

    if isinstance(conf_d, dict):
        certs_text = str(conf_d.get("certs.conf") or "")
        certs = _parse_simple_conf(certs_text)
        certs["cert_organizational_unit"] = _unit_cert_ou(unit_path)
        conf_d["certs.conf"] = _render_simple_conf(certs)
        certs = _parse_simple_conf(str(conf_d.get("certs.conf") or ""))
        certs.pop("cert_organizational_unit", None)
        certs["cert_organizational_unit"] = _unit_cert_ou(unit_path)
        conf_d["certs.conf"] = _render_simple_conf(certs)
    files = 0
    bytes_total = 0

    for kind, subdir in (("conf_d", "config.d"), ("secrets_d", "secrets.d")):
        items = data.get(kind) or {}
        for name, kv in sorted(items.items()):
            dst = root / "install" / "taks-bootstrap" / subdir / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            rows = [f"{k} = {v}" for k, v in kv.items()]
            dst.write_text("\n".join(rows) + "\n", encoding="utf-8")
            files += 1
            bytes_total += dst.stat().st_size

    return {
        "generated": "install/taks-bootstrap",
        "kind": "unit_bootstrap",
        "unit": unit_path,
        "files": files,
        "bytes": bytes_total,
    }

def _copy_repo_snapshot(dst_root: Path) -> Dict[str, Any]:
    src = repo_root_dir()
    dst = dst_root / "taks-source"
    dst.mkdir(parents=True, exist_ok=True)

    files = 0
    bytes_total = 0

    for cur_root, dirnames, filenames in os.walk(src):
        cur = Path(cur_root)
        rel_dir = cur.relative_to(src)

        dirnames[:] = sorted(
            d for d in dirnames
            if d not in REPO_EXCLUDE_NAMES
        )

        out_dir = dst / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(filenames):
            if name in REPO_EXCLUDE_NAMES:
                continue

            src_file = cur / name
            if src_file.suffix in REPO_EXCLUDE_SUFFIXES:
                continue

            rel = src_file.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(src_file.read_bytes())
            files += 1
            bytes_total += src_file.stat().st_size

    return {
        "src": str(src),
        "kind": "repo_snapshot",
        "dst": "taks-source",
        "files": files,
        "bytes": bytes_total,
        "exists": True,
    }


def _write_effective_branding(root: Path, *, unit_path: str) -> Dict[str, Any]:
    chain = _read_unit_chain(unit_path)
    if not chain:
        chain = [unit_path]

    stage_root = Path(tempfile.mkdtemp(prefix="taks-branding-chain-"))
    mounted: List[Dict[str, str]] = []

    try:
        cur = stage_root

        for idx, up in enumerate(chain):
            if idx > 0:
                cur = cur / f"child-{idx:03d}"
                cur.mkdir(parents=True, exist_ok=True)

            src_root = unit_files_root(up)
            src_branding = src_root / "branding"
            src_conf = src_root / "config.d" / "branding.conf"

            if src_branding.is_dir():
                shutil.copytree(src_branding, cur / "branding", dirs_exist_ok=True)

            if src_conf.is_file():
                conf_d = cur / "config.d"
                conf_d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_conf, conf_d / "branding.conf")

            mounted.append(
                {
                    "unit_path": up,
                    "staged_unit_dir": str(cur),
                    "src_root": str(src_root),
                    "branding_dir": str(src_branding) if src_branding.exists() else "",
                    "conf_file": str(src_conf) if src_conf.exists() else "",
                }
            )

        out_dir = root / "branding"
        if out_dir.exists():
            shutil.rmtree(out_dir)

        manifest = materialize_branding_bundle(
            tree_root=stage_root,
            current_dir=cur,
            out_dir=out_dir,
        )

        stage_to_unit = {
            str(item.get("staged_unit_dir") or ""): str(item.get("unit_path") or "")
            for item in mounted
        }

        sanitized_files = []
        for item in list(manifest.get("files", [])):
            sanitized_files.append(
                {
                    "slot": str(item.get("slot") or ""),
                    "filename": str(item.get("filename") or ""),
                    "source_unit": stage_to_unit.get(str(item.get("source_unit_dir") or ""), ""),
                    "source_name": str(item.get("source_name") or ""),
                }
            )

        sanitized_manifest = {
            "mode": "png-chain",
            "unit_path": unit_path,
            "chain": chain,
            "effective_count": int(manifest.get("effective_count", 0)),
            "files": sanitized_files,
        }

        (out_dir / "files.json").write_text(
            json.dumps(sanitized_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return {
            "generated": "branding",
            "kind": "effective_branding",
            "chain": chain,
            "mounted": mounted,
            "effective_count": int(manifest.get("effective_count", 0)),
            "files": sanitized_files,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def build_bundle_from_state(unit_path: str, role: str, bundle_name: Optional[str] = None) -> Dict[str, Any]:
    up = _safe_unit_fs(unit_path)
    role = str(role or "").strip() or "tak-node"
    bundle_name = str(bundle_name or f"{up}.tar.gz").strip()

    rendered_dir = rendered_bundles_dir()
    tar_path = rendered_dir / bundle_name

    overlays: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="taks-bundle-") as td:
        root = Path(td) / up
        root.mkdir(parents=True, exist_ok=True)

        default_src = default_bundle_dir()
        overlays.append(_copy_tree(default_src, root))

        overlays.append(_copy_repo_snapshot(root))

        role_src = role_bundle_overlay_dir(role)
        overlays.append(_copy_tree(role_src, root))

        unit_overlay = unit_bundle_overlay_dir(up)
        overlays.append(_copy_tree(unit_overlay, root))

        for src_unit in _read_unit_chain(up):
            files_root = unit_files_root(src_unit)
            for subtree in SUBTREES:
                if subtree == "branding":
                    continue
                src = files_root / subtree
                dst = root / subtree
                item = _copy_tree(src, dst)
                item["unit"] = src_unit
                item["subtree"] = subtree
                item["inherited"] = (src_unit != up)
                overlays.append(item)

        _write_unit_config(root, unit_path=up, role=role)
        overlays.append({"generated": "config/unit.json", "kind": "unit_config"})

        overlays.append(_write_node_env(root, unit_path=up))

        overlays.append(_write_effective_bootstrap(root, unit_path=up))
        overlays.append(_write_effective_branding(root, unit_path=up))

        unit_meta = _read_unit_meta(up)
        cert_model = _default_node_cert_model(unit_meta)
        if cert_model == "WILDCARD_DNS_01":
            overlays.append(_copy_wildcard_tls_material(root))

        subprocess.run(
            ["tar", "-C", str(root.parent), "-czf", str(tar_path), up],
            check=True,
        )

    return {
        "bundle_name": bundle_name,
        "tar_path": str(tar_path),
        "manifest_path": str(tar_path),
        "overlays": overlays,
    }
