from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from orchestrator_core.config import load_orch_config
from orchestrator_core.units_state import list_units


BOOTSTRAP_CONFIG_DIRNAME = "config.d"
BOOTSTRAP_SECRETS_DIRNAME = "secrets.d"


def _state_dir() -> Path:
    cfg = load_orch_config()
    return Path(cfg.paths.state_dir)


def _safe_unit_fs(unit_path: str) -> str:
    up = (unit_path or "").strip().strip("/")
    if not up:
        raise ValueError("unit_path must be non-empty")
    if "\\" in up:
        raise ValueError("invalid unit_path")
    parts = [p for p in up.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ValueError("invalid unit_path")
    return "/".join(parts)


def unit_root(unit_path: str) -> Path:
    return _state_dir() / "units" / _safe_unit_fs(unit_path)


def unit_bootstrap_root(unit_path: str) -> Path:
    return unit_root(unit_path) / "bootstrap"


def unit_bootstrap_conf_d(unit_path: str) -> Path:
    return unit_bootstrap_root(unit_path) / BOOTSTRAP_CONFIG_DIRNAME


def unit_bootstrap_secrets_d(unit_path: str) -> Path:
    return unit_bootstrap_root(unit_path) / BOOTSTRAP_SECRETS_DIRNAME


def _parse_simple_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _write_simple_kv(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{k} = {v}" for k, v in data.items()]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _parent_map() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in list_units():
        up = str(row.get("unit_path") or "").strip()
        pp = str(row.get("parent_path") or "").strip()
        if up:
            out[up] = pp
    return out


def inheritance_chain_root_to_leaf(unit_path: str) -> List[str]:
    up = _safe_unit_fs(unit_path)
    pm = _parent_map()
    chain: List[str] = []
    cur = up
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = str(pm.get(cur) or "").strip()
    chain.reverse()
    return chain


def _local_dir(unit_path: str, *, secret: bool) -> Path:
    return unit_bootstrap_secrets_d(unit_path) if secret else unit_bootstrap_conf_d(unit_path)


def _sanitize_conf_name(name: str) -> str:
    n = str(name or "").strip().lstrip("/")
    if not n:
        raise ValueError("name is required")
    parts = [p for p in n.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ValueError("invalid name")
    if any("\\" in p for p in parts):
        raise ValueError("invalid name")
    out = "/".join(parts)
    if not out.endswith(".conf"):
        raise ValueError("name must end with .conf")
    return out


def local_file_path(unit_path: str, *, secret: bool, name: str) -> Path:
    return _local_dir(unit_path, secret=secret) / _sanitize_conf_name(name)


def list_local_files(unit_path: str, *, secret: bool) -> Dict[str, Path]:
    root = _local_dir(unit_path, secret=secret)
    out: Dict[str, Path] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.conf")):
        if p.is_file():
            out[str(p.relative_to(root))] = p
    return out


def local_file_texts(unit_path: str, *, secret: bool) -> Dict[str, str]:
    return {name: p.read_text(encoding="utf-8") for name, p in list_local_files(unit_path, secret=secret).items()}


def effective_kv_by_file(unit_path: str, *, secret: bool) -> Dict[str, Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {}
    for src_unit in inheritance_chain_root_to_leaf(unit_path):
        for name, p in list_local_files(src_unit, secret=secret).items():
            cur = merged.setdefault(name, {})
            cur.update(_parse_simple_kv(p))
    return merged


def effective_file_texts(unit_path: str, *, secret: bool) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, kv in effective_kv_by_file(unit_path, secret=secret).items():
        rows = [f"{k} = {v}" for k, v in kv.items()]
        out[name] = "\n".join(rows) + ("\n" if rows else "")
    return out


def list_effective_sources(unit_path: str, *, secret: bool) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for src_unit in inheritance_chain_root_to_leaf(unit_path):
        for name in list_local_files(src_unit, secret=secret).keys():
            out.setdefault(name, []).append(src_unit)
    return out


def write_local_file(unit_path: str, *, secret: bool, name: str, content: str) -> Path:
    p = local_file_path(unit_path, secret=secret, name=name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content or ""), encoding="utf-8")
    return p


def delete_local_file(unit_path: str, *, secret: bool, name: str) -> Path:
    p = local_file_path(unit_path, secret=secret, name=name)
    if not p.exists():
        raise FileNotFoundError(str(p))
    p.unlink()
    root = _local_dir(unit_path, secret=secret)
    parent = p.parent
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return p


def effective_bootstrap_for_bundle(unit_path: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    return {
        "conf_d": effective_kv_by_file(unit_path, secret=False),
        "secrets_d": effective_kv_by_file(unit_path, secret=True),
    }
