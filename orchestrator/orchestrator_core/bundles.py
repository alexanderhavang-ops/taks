from __future__ import annotations

import json
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")


def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def bundles_dir() -> Path:
    d = Path(os.environ.get("TAKS_BUNDLE_DIR") or str(_state_dir() / "bundles"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def rendered_bundles_dir() -> Path:
    d = bundles_dir() / "rendered"
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


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _read_unit_meta(unit_path: str) -> Dict[str, Any]:
    p = _unit_json_path(unit_path)
    if not p.exists():
        return {}
    try:
        j = _read_json(p)
    except Exception:
        return {}
    return j if isinstance(j, dict) else {}


def _unit_parent(unit_path: str) -> str:
    j = _read_unit_meta(unit_path)
    return str(j.get("parent_path") or "").strip()


def _unit_chain_root_to_leaf(unit_path: str) -> List[str]:
    """
    Follow parent_path until root and return [root, ..., leaf].
    """
    leaf = _safe_unit_fs(unit_path)
    seen = set()
    chain_rev: List[str] = []
    cur = leaf

    while cur:
        if cur in seen:
            raise ValueError(f"cycle in unit parent chain at {cur}")
        seen.add(cur)
        chain_rev.append(cur)
        cur = _unit_parent(cur)

    chain_rev.reverse()
    return chain_rev


def _copy_tree(src: Path, dst: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"src": str(src), "files": 0, "bytes": 0, "exists": src.exists()}
    if not src.exists():
        return out
    if not src.is_dir():
        raise ValueError(f"overlay is not a directory: {src}")

    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not p.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        data = p.read_bytes()
        target.write_bytes(data)
        try:
            os.chmod(target, p.stat().st_mode & 0o777)
        except Exception:
            pass
        out["files"] += 1
        out["bytes"] += len(data)
    return out


def _copy_unit_subtree(src: Path, dst: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"src": str(src), "files": 0, "bytes": 0, "exists": src.exists()}
    if not src.exists():
        return out
    if not src.is_dir():
        raise ValueError(f"unit subtree is not a directory: {src}")

    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not p.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        data = p.read_bytes()
        target.write_bytes(data)
        try:
            os.chmod(target, p.stat().st_mode & 0o777)
        except Exception:
            pass
        out["files"] += 1
        out["bytes"] += len(data)
    return out


def _write_unit_config(root: Path, *, unit_path: str, role: str, chain: List[str]) -> Path:
    unit_meta = _read_unit_meta(unit_path)
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
    }

    out = config_dir / "unit.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


@dataclass
class BuildResult:
    bundle_name: str
    tar_path: Path
    manifest_path: Path
    overlays: List[Dict[str, Any]]


def build_bundle_from_state(
    *,
    unit_path: str,
    role: str,
    bundle_name: Optional[str] = None,
) -> BuildResult:
    """
    Build bundle tarball from:

      1) default_bundle/
      2) roles/<role>/bundle/
      3) units/<unit>/bundle/
      4) inherited unit file subtrees root->leaf:
         packages, branding, users, plugins, maps, missions, misc

    KISS:
      - always rebuild
      - overwrite tarball
      - no fingerprint
      - no external manifest file
    """

    up = _safe_unit_fs(unit_path)
    r = (role or "").strip()
    if not r:
        raise ValueError("role must be non-empty")

    base = (bundle_name or f"{up}-{r}-bundle").strip()
    if base.endswith(".tar.gz"):
        tar_name = base
        bundle_root = base[:-len(".tar.gz")]
    else:
        tar_name = base + ".tar.gz"
        bundle_root = base

    out_tar = rendered_bundles_dir() / tar_name

    overlays: List[Dict[str, Any]] = []

    default_src = default_bundle_dir()
    role_src = role_bundle_overlay_dir(r)
    unit_src = unit_bundle_overlay_dir(up)

    chain = _unit_chain_root_to_leaf(up)

    with tempfile.TemporaryDirectory(prefix="taks-bundle-") as td:
        td_path = Path(td)
        root = td_path / bundle_root
        root.mkdir(parents=True, exist_ok=True)

        overlays.append(_copy_tree(default_src, root))
        overlays.append(_copy_tree(role_src, root))
        overlays.append(_copy_tree(unit_src, root))

        for subtree in SUBTREES:
            dst_root = root / subtree
            dst_root.mkdir(parents=True, exist_ok=True)

            for unit_id in chain:
                src_root = unit_files_root(unit_id) / subtree
                stat = _copy_unit_subtree(src_root, dst_root)
                stat["unit"] = unit_id
                stat["subtree"] = subtree
                overlays.append(stat)

        unit_cfg = _write_unit_config(root, unit_path=up, role=r, chain=chain)
        overlays.append({
            "generated": str(unit_cfg.relative_to(root)),
            "kind": "unit_config",
        })

        tmp_tar = out_tar.parent / (out_tar.name + ".tmp")
        with tarfile.open(tmp_tar, "w:gz") as tf:
            tf.add(str(root), arcname=bundle_root)

        os.replace(tmp_tar, out_tar)

    return BuildResult(
        bundle_name=tar_name,
        tar_path=out_tar,
        manifest_path=out_tar,
        overlays=overlays,
    )
