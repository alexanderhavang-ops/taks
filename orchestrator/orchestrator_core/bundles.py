from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from orchestrator_core.branding_resolver import materialize_branding_bundle
from orchestrator_core.bundle_verify import verify_bundle_tree
from orchestrator_core.config import load_orch_config, load_secrets_config
from orchestrator_core.unit_bootstrap import effective_bootstrap_for_bundle
from orchestrator_core.units_state import ensure_unit_orchestrator_secret


UI_SUBTREES = ("branding", "packages", "users", "plugins", "maps", "missions", "documents", "misc", "logos")

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
    ".orig",
    ".rej",
    ".tar.gz",
    ".zip",
}

FORBIDDEN_NAME_FRAGMENTS = (".bak.",)
FORBIDDEN_NAME_SUFFIXES = ("~",)


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


def _resolve_existing_unit_dir(unit_path: str) -> Path:
    safe = _safe_unit_fs(unit_path)
    base = units_dir()

    candidates: List[Path] = []
    for cand in (base / safe, base / safe.lower()):
        if cand not in candidates:
            candidates.append(cand)

    if base.exists():
        for cand in sorted(base.iterdir()):
            if cand.is_dir() and cand.name.casefold() == safe.casefold() and cand not in candidates:
                candidates.append(cand)

    with_unit_json = [cand for cand in candidates if (cand / "unit.json").is_file()]
    if len(with_unit_json) == 1:
        return with_unit_json[0]
    if len(with_unit_json) > 1:
        exact = [cand for cand in with_unit_json if cand.name == safe]
        if len(exact) == 1:
            return exact[0]
        lower = [cand for cand in with_unit_json if cand.name == safe.lower()]
        if len(lower) == 1:
            return lower[0]
        names = ", ".join(cand.name for cand in with_unit_json)
        raise ValueError(f"ambiguous unit directory for {unit_path}: multiple unit.json matches: {names}")

    existing = [cand for cand in candidates if cand.exists()]
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        exact = [cand for cand in existing if cand.name == safe]
        if len(exact) == 1:
            return exact[0]
        lower = [cand for cand in existing if cand.name == safe.lower()]
        if len(lower) == 1:
            return lower[0]
        names = ", ".join(cand.name for cand in existing)
        raise ValueError(f"ambiguous unit directory for {unit_path}: {names}")

    return base / safe


def _unit_dir(unit_path: str) -> Path:
    return _resolve_existing_unit_dir(unit_path)


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
    cur = _safe_unit_fs(unit_path)
    seen = set()

    while cur:
        key = cur.casefold()
        if key in seen:
            break
        seen.add(key)

        resolved_dir = _unit_dir(cur)
        canonical = resolved_dir.name if resolved_dir.exists() else cur
        chain.append(canonical)

        raw = _read_unit_json(canonical)
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


def _default_le_email(unit_meta: Dict[str, Any]) -> str:
    meta = unit_meta if isinstance(unit_meta, dict) else {}
    explicit = _meta_get(meta, "le_email", "letsencrypt_email")
    if explicit:
        return explicit
    return ""


def _unit_cert_ou(unit_path: str) -> str:
    safe = _safe_unit_fs(unit_path)
    return safe.split("/")[-1].strip() or safe


def _render_simple_conf(rows: Dict[str, str]) -> str:
    keys = sorted(rows.keys())
    return "".join(f"{k} = {rows[k]}\n" for k in keys if str(rows[k]).strip() != "")


def _is_junk_name(name: str) -> bool:
    if not name:
        return False
    if name in REPO_EXCLUDE_NAMES:
        return True
    if any(fragment in name for fragment in FORBIDDEN_NAME_FRAGMENTS):
        return True
    if any(name.endswith(suffix) for suffix in FORBIDDEN_NAME_SUFFIXES):
        return True
    return False


def _should_skip_repo_dir(name: str) -> bool:
    return _is_junk_name(name) or name in REPO_EXCLUDE_NAMES


def _should_skip_repo_file(name: str) -> bool:
    if _is_junk_name(name):
        return True
    suffixes = Path(name).suffixes
    joined = "".join(suffixes[-2:]) if len(suffixes) >= 2 else ""
    if joined in REPO_EXCLUDE_SUFFIXES:
        return True
    if suffixes and suffixes[-1] in REPO_EXCLUDE_SUFFIXES:
        return True
    return False


def _should_skip_tree_file(name: str, *, allow_suffixes: Sequence[str] = ()) -> bool:
    if not _should_skip_repo_file(name):
        return False

    suffixes = Path(name).suffixes
    joined = "".join(suffixes[-2:]) if len(suffixes) >= 2 else ""
    allowed = {str(x) for x in (allow_suffixes or ()) if str(x)}

    if joined in allowed:
        return False
    if suffixes and suffixes[-1] in allowed:
        return False

    return True


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_file(src: Path, dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return src.stat().st_size


def _copy_tree_filtered(src: Path, dst: Path) -> Dict[str, Any]:
    files = 0
    bytes_total = 0

    if not src.exists():
        return {"src": str(src), "files": 0, "bytes": 0, "exists": False}

    for cur_root, dirnames, filenames in os.walk(src):
        cur = Path(cur_root)
        rel_dir = cur.relative_to(src)

        dirnames[:] = sorted(d for d in dirnames if not _should_skip_repo_dir(d))
        out_dir = dst / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(filenames):
            if _should_skip_repo_file(name):
                continue
            src_file = cur / name
            out_file = out_dir / name
            bytes_total += _copy_file(src_file, out_file)
            files += 1

    return {"src": str(src), "files": files, "bytes": bytes_total, "exists": True}


def _copy_tree_into(
    src: Path,
    dst: Path,
    *,
    skip_file_predicate=None,
    allow_suffixes: Sequence[str] = (),
) -> Dict[str, Any]:
    files = 0
    bytes_total = 0

    if not src.exists():
        return {"src": str(src), "files": 0, "bytes": 0, "exists": False}

    for cur_root, dirnames, filenames in os.walk(src):
        cur = Path(cur_root)
        rel_dir = cur.relative_to(src)

        dirnames[:] = sorted(d for d in dirnames if not _should_skip_repo_dir(d))
        out_dir = dst / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(filenames):
            if _should_skip_tree_file(name, allow_suffixes=allow_suffixes):
                continue
            rel_file = rel_dir / name
            if skip_file_predicate is not None and skip_file_predicate(rel_file):
                continue
            src_file = cur / name
            out_file = out_dir / name
            bytes_total += _copy_file(src_file, out_file)
            files += 1

    return {"src": str(src), "files": files, "bytes": bytes_total, "exists": True}


def _copy_repo_snapshot(dst_root: Path) -> Dict[str, Any]:
    src = repo_root_dir()
    dst = dst_root / "taks-source"
    _reset_dir(dst)
    result = _copy_tree_filtered(src, dst)
    result.update(
        {
            "kind": "repo_snapshot",
            "dst": "taks-source",
        }
    )
    return result


def _subtree_source_dirs(unit_path: str, role: str, subtree: str) -> List[Path]:
    dirs: List[Path] = [
        default_bundle_dir() / subtree,
        role_bundle_overlay_dir(role) / subtree,
    ]
    for src_unit in _read_unit_chain(unit_path):
        dirs.append(unit_files_root(src_unit) / subtree)
        dirs.append(unit_bundle_overlay_dir(src_unit) / subtree)
    return dirs


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
        "unit": unit_path,
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


def _write_effective_bootstrap(root: Path, *, unit_path: str) -> Dict[str, Any]:
    ensure_unit_orchestrator_secret(unit_path)
    data = effective_bootstrap_for_bundle(unit_path)
    conf_d = dict((data.get("conf_d") or {}) if isinstance(data, dict) else {})
    secrets_d = dict((data.get("secrets_d") or {}) if isinstance(data, dict) else {})

    certs = dict(conf_d.get("certs.conf") or {})
    certs["cert_organizational_unit"] = _unit_cert_ou(unit_path)
    conf_d["certs.conf"] = certs

    files = 0
    bytes_total = 0

    for items, subdir in ((conf_d, "config.d"), (secrets_d, "secrets.d")):
        if not isinstance(items, dict):
            continue
        for name, kv in sorted(items.items()):
            dst = root / "install" / "taks-bootstrap" / subdir / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = _render_simple_conf(dict(kv or {}))
            dst.write_text(content, encoding="utf-8")
            files += 1
            bytes_total += dst.stat().st_size

    return {
        "generated": "install/taks-bootstrap",
        "kind": "unit_bootstrap",
        "unit": unit_path,
        "files": files,
        "bytes": bytes_total,
    }


def _find_letsencrypt_artifact_dir(unit_path: str) -> Path:
    unit_meta = _read_unit_meta(unit_path)
    fqdn = _default_node_fqdn(unit_path, unit_meta)
    cfg = load_orch_config()

    base = Path(cfg.letsencrypt.artifact_cert_dir)
    candidates = [
        base / fqdn,
        base,
    ]

    for cand in candidates:
        if (cand / "fullchain.pem").is_file() and (cand / "privkey.pem").is_file():
            return cand

    tried = ", ".join(str(c) for c in candidates)
    raise ValueError(f"missing letsencrypt artifact cert pair for {fqdn}; tried: {tried}")


def _copy_letsencrypt_tls_material(root: Path, *, unit_path: str) -> Dict[str, Any]:
    src_dir = _find_letsencrypt_artifact_dir(unit_path)
    dst_dir = root / "install" / "letsencrypt"
    _reset_dir(dst_dir)

    dst_cert = dst_dir / "fullchain.pem"
    dst_key = dst_dir / "privkey.pem"
    bytes_total = 0
    bytes_total += _copy_file(src_dir / "fullchain.pem", dst_cert)
    bytes_total += _copy_file(src_dir / "privkey.pem", dst_key)

    return {
        "kind": "letsencrypt_tls_material",
        "src_dir": str(src_dir),
        "dst_cert": "install/letsencrypt/fullchain.pem",
        "dst_key": "install/letsencrypt/privkey.pem",
        "files": 2,
        "bytes": bytes_total,
    }


def _first_existing_dir(candidates: Sequence[Path]) -> Optional[Path]:
    for p in candidates:
        if p.is_dir():
            return p
    return None


def _first_existing_file(candidates: Sequence[Path]) -> Optional[Path]:
    for p in candidates:
        if p.is_file():
            return p
    return None


def _branding_dir_candidates(unit_path: str) -> List[Path]:
    return [
        unit_files_root(unit_path) / "branding",
        _unit_dir(unit_path) / "branding",
    ]


def _branding_conf_candidates(unit_path: str) -> List[Path]:
    return [
        unit_files_root(unit_path) / "config.d" / "branding.conf",
        _unit_dir(unit_path) / "config.d" / "branding.conf",
    ]


def _branding_meta_candidates(unit_path: str) -> List[Path]:
    return [
        unit_files_root(unit_path) / "branding" / "brand.json",
        _unit_dir(unit_path) / "assets" / "brand.json",
        _unit_dir(unit_path) / "branding" / "brand.json",
    ]


def _materialize_effective_branding_dir(out_dir: Path, *, unit_path: str) -> Dict[str, Any]:
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

            src_branding = _first_existing_dir(_branding_dir_candidates(up))
            src_conf = _first_existing_file(_branding_conf_candidates(up))

            if src_branding is not None:
                shutil.copytree(src_branding, cur / "branding", dirs_exist_ok=True)

            if src_conf is not None:
                conf_d = cur / "config.d"
                conf_d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_conf, conf_d / "branding.conf")

            mounted.append(
                {
                    "unit_path": up,
                    "staged_unit_dir": str(cur),
                    "branding_dir": str(src_branding) if src_branding is not None else "",
                    "conf_file": str(src_conf) if src_conf is not None else "",
                }
            )

        _reset_dir(out_dir)

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

        effective_brand_meta: Dict[str, Any] = {}
        effective_brand_meta_source = ""
        effective_brand_meta_unit = ""

        for item in reversed(mounted):
            up = str(item.get("unit_path") or "")
            for candidate in _branding_meta_candidates(up):
                if not candidate.is_file():
                    continue
                try:
                    loaded = json.loads(candidate.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(loaded, dict):
                    effective_brand_meta = loaded
                    effective_brand_meta_source = str(candidate)
                    effective_brand_meta_unit = up
                    break
            if effective_brand_meta:
                break

        sanitized_manifest = {
            "mode": "png-chain",
            "unit_path": unit_path,
            "chain": chain,
            "effective_count": int(manifest.get("effective_count", 0)),
            "files": sanitized_files,
        }

        if effective_brand_meta_source:
            sanitized_manifest["brand_meta_source"] = effective_brand_meta_source

        (out_dir / "files.json").write_text(
            json.dumps(sanitized_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if effective_brand_meta:
            (out_dir / "brand.json").write_text(
                json.dumps(effective_brand_meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        emitted_by_name = {
            str(item.get("filename") or ""): item
            for item in sanitized_files
            if str(item.get("filename") or "")
        }

        items: List[Dict[str, Any]] = []
        for p in sorted(out_dir.rglob("*")):
            if not p.is_file():
                continue

            relname = str(p.relative_to(out_dir))
            base: Dict[str, Any] = {
                "path": relname,
                "bytes": p.stat().st_size,
                "resolved_path": str(p),
            }

            emitted = emitted_by_name.get(relname)
            if emitted is not None:
                src_unit = str(emitted.get("source_unit") or "")
                inherited = src_unit != unit_path
                base.update(
                    {
                        "kind": "inherited" if inherited else "local",
                        "inherited": inherited,
                        "source_unit": src_unit,
                        "source_name": str(emitted.get("source_name") or ""),
                        "slot": str(emitted.get("slot") or ""),
                    }
                )
            elif relname == "brand.json":
                inherited = bool(effective_brand_meta_unit and effective_brand_meta_unit != unit_path)
                base.update(
                    {
                        "kind": "inherited" if inherited else "local",
                        "inherited": inherited,
                        "source_unit": effective_brand_meta_unit or "generated",
                        "source_name": Path(effective_brand_meta_source).name if effective_brand_meta_source else "",
                    }
                )
            else:
                base.update(
                    {
                        "kind": "generated",
                        "inherited": True,
                        "source_unit": "generated",
                    }
                )

            items.append(base)

        return {
            "generated": "branding",
            "kind": "effective_branding",
            "chain": chain,
            "mounted": mounted,
            "effective_count": int(manifest.get("effective_count", 0)),
            "files": sanitized_files,
            "brand_meta_source": effective_brand_meta_source,
            "brand_meta_source_unit": effective_brand_meta_unit,
            "items": items,
        }
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def list_effective_branding_subtree_items(unit_path: str) -> List[Dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="taks-branding-list-") as td:
        result = _materialize_effective_branding_dir(Path(td) / "branding", unit_path=unit_path)
        out: List[Dict[str, Any]] = []
        for item in list(result.get("items") or []):
            row = dict(item)
            row.pop("resolved_path", None)
            out.append(row)
        return out


def resolve_effective_branding_subtree_file(unit_path: str, relname: str) -> Optional[Dict[str, Any]]:
    td = tempfile.mkdtemp(prefix="taks-branding-download-")
    try:
        result = _materialize_effective_branding_dir(Path(td) / "branding", unit_path=unit_path)
        for item in list(result.get("items") or []):
            if str(item.get("path") or "") == relname:
                row = dict(item)
                row["cleanup_dir"] = td
                return row
        shutil.rmtree(td, ignore_errors=True)
        return None
    except Exception:
        shutil.rmtree(td, ignore_errors=True)
        raise


def _write_effective_branding(root: Path, *, unit_path: str) -> Dict[str, Any]:
    result = _materialize_effective_branding_dir(root / "branding", unit_path=unit_path)
    return {
        "generated": "branding",
        "kind": "effective_branding",
        "chain": list(result.get("chain") or []),
        "mounted": list(result.get("mounted") or []),
        "effective_count": int(result.get("effective_count", 0)),
        "files": list(result.get("files") or []),
        "brand_meta_source": str(result.get("brand_meta_source") or ""),
    }


def _materialize_generic_subtree(root: Path, *, unit_path: str, role: str, subtree: str) -> Dict[str, Any]:
    dst = root / subtree
    _reset_dir(dst)

    sources = _subtree_source_dirs(unit_path, role, subtree)
    copied: List[Dict[str, Any]] = []
    total_files = 0
    total_bytes = 0

    for src in sources:
        item = _copy_tree_into(src, dst, allow_suffixes=(".zip",))
        total_files += int(item.get("files", 0))
        total_bytes += int(item.get("bytes", 0))
        if item.get("exists"):
            copied.append(item)

    return {
        "generated": subtree,
        "kind": "effective_subtree",
        "subtree": subtree,
        "sources": copied,
        "files": total_files,
        "bytes": total_bytes,
    }


def _is_takserver_deb_path(rel_file: Path) -> bool:
    return rel_file.name.startswith("takserver_") and rel_file.name.endswith("_all.deb")


def _select_takserver_deb(sources: Sequence[Path]) -> Path:
    chosen: Optional[Path] = None

    for src in sources:
        if not src.exists():
            continue
        matches = [p for p in sorted(src.rglob("takserver_*_all.deb")) if p.is_file() and not _should_skip_repo_file(p.name)]
        if len(matches) > 1:
            names = ", ".join(str(p.relative_to(src)) for p in matches)
            raise ValueError(f"packages subtree has multiple takserver debs in {src}: {names}")
        if len(matches) == 1:
            chosen = matches[0]

    if chosen is None:
        raise ValueError("packages subtree missing takserver_*_all.deb across all sources")

    return chosen


def _materialize_packages_subtree(root: Path, *, unit_path: str, role: str) -> Dict[str, Any]:
    dst = root / "packages"
    _reset_dir(dst)

    sources = _subtree_source_dirs(unit_path, role, "packages")
    chosen_deb = _select_takserver_deb(sources)

    copied: List[Dict[str, Any]] = []
    total_files = 0
    total_bytes = 0

    for src in sources:
        item = _copy_tree_into(src, dst, skip_file_predicate=_is_takserver_deb_path, allow_suffixes=(".zip",))
        total_files += int(item.get("files", 0))
        total_bytes += int(item.get("bytes", 0))
        if item.get("exists"):
            copied.append(item)

    total_bytes += _copy_file(chosen_deb, dst / chosen_deb.name)
    total_files += 1

    debs = sorted(dst.glob("takserver_*_all.deb"))
    if len(debs) != 1:
        raise ValueError(f"materialized packages subtree must contain exactly one takserver deb, found {len(debs)}")

    return {
        "generated": "packages",
        "kind": "effective_packages",
        "sources": copied,
        "selected_takserver_deb": chosen_deb.name,
        "files": total_files,
        "bytes": total_bytes,
    }


def _materialize_bundle_tree(root: Path, *, unit_path: str, role: str) -> Dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)

    overlays: List[Dict[str, Any]] = []

    overlays.append(_copy_tree_filtered(default_bundle_dir(), root))

    if load_orch_config().bundles.include_taks_source:
        overlays.append(_copy_repo_snapshot(root))

    overlays.append(_copy_tree_filtered(role_bundle_overlay_dir(role), root))
    overlays.append(_copy_tree_filtered(unit_bundle_overlay_dir(unit_path), root))

    overlays.append({"generated": "config/unit.json", "kind": "unit_config", "path": str(_write_unit_config(root, unit_path=unit_path, role=role))})
    overlays.append(_write_node_env(root, unit_path=unit_path))
    overlays.append(_write_effective_bootstrap(root, unit_path=unit_path))

    for subtree in UI_SUBTREES:
        if subtree == "branding":
            overlays.append(_write_effective_branding(root, unit_path=unit_path))
        elif subtree == "packages":
            overlays.append(_materialize_packages_subtree(root, unit_path=unit_path, role=role))
        else:
            overlays.append(_materialize_generic_subtree(root, unit_path=unit_path, role=role, subtree=subtree))

    overlays.append(_copy_letsencrypt_tls_material(root, unit_path=unit_path))

    return {
        "bundle_root": str(root),
        "overlays": overlays,
    }


def bundle_readiness(unit_path: str, role: str) -> Dict[str, Any]:
    up = _safe_unit_fs(unit_path)
    role = str(role or "").strip() or "tak-node"

    derived = {
        "cert_organizational_unit": _unit_cert_ou(up),
        "fqdn": _default_node_fqdn(up, _read_unit_meta(up)),
        "node_cert_model": _default_node_cert_model(_read_unit_meta(up)),
    }

    try:
        with tempfile.TemporaryDirectory(prefix="taks-bundle-readiness-") as td:
            root = Path(td) / up
            _materialize_bundle_tree(root, unit_path=up, role=role)
            report = verify_bundle_tree(root, unit_path=up, role=role)
            report["derived"] = {**derived, **dict(report.get("derived") or {})}
            report["missing"] = list(report.get("errors") or [])
            return report
    except Exception as e:
        msg = str(e)
        return {
            "ok": False,
            "missing": [msg],
            "errors": [msg],
            "warnings": [],
            "derived": derived,
        }


def build_bundle_from_state(unit_path: str, role: str, bundle_name: Optional[str] = None) -> Dict[str, Any]:
    up = _safe_unit_fs(unit_path)
    role = str(role or "").strip() or "tak-node"
    bundle_name = str(bundle_name or f"{up}.tar.gz").strip()

    rendered_dir = rendered_bundles_dir()
    tar_path = rendered_dir / bundle_name

    with tempfile.TemporaryDirectory(prefix="taks-bundle-") as td:
        root = Path(td) / up
        materialized = _materialize_bundle_tree(root, unit_path=up, role=role)
        report = verify_bundle_tree(root, unit_path=up, role=role)
        if not bool(report.get("ok")):
            errors = "; ".join(str(x) for x in (report.get("errors") or []))
            raise RuntimeError(f"bundle verify failed for {up}: {errors}")

        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(root, arcname=up)

    return {
        "bundle_name": bundle_name,
        "tar_path": str(tar_path),
        "manifest_path": str(tar_path),
        "overlays": materialized.get("overlays") or [],
        "verify": report,
    }
