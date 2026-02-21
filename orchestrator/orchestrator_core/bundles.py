from __future__ import annotations

import json
import os
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _state_dir() -> Path:
    return Path(os.environ.get("TAKS_STATE_DIR") or "/opt/tak-orch/state")


def bundles_dir() -> Path:
    d = Path(os.environ.get("TAKS_BUNDLE_DIR") or str(_state_dir() / "bundles"))
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
    """
    Built-in base bundle content, shipped in source:
      orchestrator/orchestrator_core/default_bundle/
    """
    return Path(__file__).resolve().parent / "default_bundle"


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _safe_unit_fs(unit_path: str) -> str:
    up = (unit_path or "").strip().strip("/")
    if not up:
        raise ValueError("unit_path must be non-empty")
    return up


def unit_bundle_overlay_dir(unit_path: str) -> Path:
    up = _safe_unit_fs(unit_path)
    return units_dir() / up / "bundle"


def role_bundle_overlay_dir(role: str) -> Path:
    r = (role or "").strip()
    if not r:
        raise ValueError("role must be non-empty")
    return roles_dir() / r / "bundle"


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


def _manifest_from_root(root_dir: Path, bundle_root_name: str) -> Dict[str, Any]:
    dirs: List[str] = []
    if root_dir.exists():
        for p in sorted(root_dir.iterdir()):
            if p.is_dir():
                dirs.append(p.name + "/")

    return {
        "version": 1,
        "name": bundle_root_name.rstrip("/"),
        "description": "TAKS bundle built from default + role + unit overlays.",
        "built_utc": _utc_iso(root_dir.stat().st_mtime) if root_dir.exists()
        else _utc_iso(datetime.now(tz=timezone.utc).timestamp()),
        "layout": {
            "root": bundle_root_name if bundle_root_name.endswith("/") else bundle_root_name + "/",
            "directories": dirs,
        },
    }


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
      3) units/<unit_path>/bundle/
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

    out_tar = bundles_dir() / tar_name
    out_manifest = bundles_dir() / (bundle_root + ".manifest.json")

    overlays: List[Dict[str, Any]] = []

    default_src = default_bundle_dir()
    role_src = role_bundle_overlay_dir(r)
    unit_src = unit_bundle_overlay_dir(up)

    with tempfile.TemporaryDirectory(prefix="taks-bundle-") as td:
        td_path = Path(td)
        root = td_path / bundle_root
        root.mkdir(parents=True, exist_ok=True)

        # Layering order:
        overlays.append(_copy_tree(default_src, root))
        overlays.append(_copy_tree(role_src, root))
        overlays.append(_copy_tree(unit_src, root))

        manifest = _manifest_from_root(root, bundle_root + "/")
        out_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        with tarfile.open(out_tar, "w:gz") as tf:
            tf.add(str(root), arcname=bundle_root)

    return BuildResult(
        bundle_name=tar_name,
        tar_path=out_tar,
        manifest_path=out_manifest,
        overlays=overlays,
    )

