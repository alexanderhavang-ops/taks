from __future__ import annotations

import json
import os
import tarfile
from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.unit_bootstrap import effective_bootstrap_for_bundle
import tempfile
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
    explicit = _meta_get(meta, "node_fqdn", "taks_node_fqdn", "fqdn")
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


def bundle_readiness(unit_path: str, role: str) -> Dict[str, Any]:
    data = effective_bootstrap_for_bundle(unit_path)
    conf_d = (data.get("conf_d") or {}) if isinstance(data, dict) else {}
    secrets_d = (data.get("secrets_d") or {}) if isinstance(data, dict) else {}

    certs_obj = conf_d.get("certs.conf") or {}
    if isinstance(certs_obj, dict):
        certs = {str(k).strip(): str(v).strip() for k, v in certs_obj.items()}
    else:
        certs = _parse_simple_conf(str(certs_obj))

    takctl_conf_obj = conf_d.get("takctl.conf") or {}
    if isinstance(takctl_conf_obj, dict):
        takctl_conf = {str(k).strip(): str(v).strip() for k, v in takctl_conf_obj.items()}
    else:
        takctl_conf = _parse_simple_conf(str(takctl_conf_obj))

    takctl_sec_obj = secrets_d.get("takctl.conf") or {}
    if isinstance(takctl_sec_obj, dict):
        takctl_sec = {str(k).strip(): str(v).strip() for k, v in takctl_sec_obj.items()}
    else:
        takctl_sec = _parse_simple_conf(str(takctl_sec_obj))

    certs_sec_obj = secrets_d.get("certs.conf") or {}
    if isinstance(certs_sec_obj, dict):
        certs_sec = {str(k).strip(): str(v).strip() for k, v in certs_sec_obj.items()}
    else:
        certs_sec = _parse_simple_conf(str(certs_sec_obj))

    murmur_sec_obj = secrets_d.get("murmur.conf") or {}
    if isinstance(murmur_sec_obj, dict):
        murmur_sec = {str(k).strip(): str(v).strip() for k, v in murmur_sec_obj.items()}
    else:
        murmur_sec = _parse_simple_conf(str(murmur_sec_obj))

    required_cert_keys = (
        "cert_country",
        "cert_state",
        "cert_city",
        "cert_organization",
    )
    missing_cert = [k for k in required_cert_keys if not str(certs.get(k) or "").strip()]

    required_bootstrap = [
        ("conf.d/takctl.conf:takctl_admin_user", str(takctl_conf.get("takctl_admin_user") or "").strip()),
        ("secrets.d/takctl.conf:takctl_admin_password", str(takctl_sec.get("takctl_admin_password") or "").strip()),
        ("secrets.d/certs.conf:cert_capass", str(certs_sec.get("cert_capass") or "").strip()),
        ("secrets.d/certs.conf:cert_pass", str(certs_sec.get("cert_pass") or "").strip()),
        ("secrets.d/murmur.conf:serverpassword", str(murmur_sec.get("serverpassword") or "").strip()),
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
    return os.environ.get("LE_EMAIL", "").strip()


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


def _write_node_env(root: Path, *, unit_path: str) -> Path:
    unit_meta = _read_unit_meta(unit_path)
    fqdn = _default_node_fqdn(unit_path, unit_meta)
    cert_model = _default_node_cert_model(unit_meta)
    le_email = _default_le_email(unit_meta)

    cfg = load_orch_config()
    secrets = load_secrets_config()

    install_dir = root / "install"
    install_dir.mkdir(parents=True, exist_ok=True)

    orch_base = str(cfg.identity.public_base_url).strip().rstrip("/")
    if orch_base:
        orch_api_url = orch_base
    else:
        orch_api_url = ""

    rows = [
        "# Generated by TAKS orchestrator bundle builder",
        f"TAKS_NODE_FQDN={fqdn}",
        f"TAKS_NODE_CERT_MODEL={cert_model}",
    ]

    if le_email:
        rows.append(f"LE_EMAIL={le_email}")

    if orch_api_url:
        rows.append(f"ORCH_API_URL={orch_api_url}")

    rows.append(f"TAKS_NODE_USER={secrets.auth.node_api_user}")
    rows.append(f"TAKS_NODE_PASSWORD={secrets.auth.node_api_password}")

    out = install_dir / "node.env"
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return out


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

    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)

        if any(part in REPO_EXCLUDE_NAMES for part in rel.parts):
            continue
        if p.suffix in REPO_EXCLUDE_SUFFIXES:
            continue

        out = dst / rel
        if p.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if p.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(p.read_bytes())
            files += 1
            bytes_total += p.stat().st_size

    return {
        "src": str(src),
        "kind": "repo_snapshot",
        "dst": "taks-source",
        "files": files,
        "bytes": bytes_total,
        "exists": True,
    }


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
                src = files_root / subtree
                dst = root / subtree
                item = _copy_tree(src, dst)
                item["unit"] = src_unit
                item["subtree"] = subtree
                item["inherited"] = (src_unit != up)
                overlays.append(item)

        _write_unit_config(root, unit_path=up, role=role)
        overlays.append({"generated": "config/unit.json", "kind": "unit_config"})

        _write_node_env(root, unit_path=up)
        overlays.append({"generated": "install/node.env", "kind": "node_env"})

        overlays.append(_write_effective_bootstrap(root, unit_path=up))

        unit_meta = _read_unit_meta(up)
        cert_model = _default_node_cert_model(unit_meta)
        if cert_model == "WILDCARD_DNS_01":
            overlays.append(_copy_wildcard_tls_material(root))

        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(root, arcname=up)

    return {
        "bundle_name": bundle_name,
        "tar_path": str(tar_path),
        "manifest_path": str(tar_path),
        "overlays": overlays,
    }
