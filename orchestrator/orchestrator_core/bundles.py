from __future__ import annotations

import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def artifacts_dir() -> Path:
    d = _state_dir() / "artifacts"
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


def _copy_artifact_payload(src: Path, dst: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {"src": str(src), "files": 0, "bytes": 0, "exists": src.exists()}

    payload_root = src / "current" if (src / "current").is_dir() else src
    if not payload_root.exists():
        return out
    if not payload_root.is_dir():
        raise ValueError(f"artifact payload is not a directory: {payload_root}")

    for p in sorted(payload_root.rglob("*")):
        rel = p.relative_to(payload_root)
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

    out["src"] = str(payload_root)
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
      3) units/<unit_path>/bundle/
      4) global artifacts/<name>/[current/]... -> packages/<name>/

    Output:
      /opt/tak-orch/state/bundles/rendered/<unit>.tar.gz

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

    with tempfile.TemporaryDirectory(prefix="taks-bundle-") as td:
        td_path = Path(td)
        root = td_path / bundle_root
        root.mkdir(parents=True, exist_ok=True)

        overlays.append(_copy_tree(default_src, root))
        overlays.append(_copy_tree(role_src, root))
        overlays.append(_copy_tree(unit_src, root))

        packages_root = root / "packages"
        packages_root.mkdir(parents=True, exist_ok=True)

        for name in ("takserver", "taks", "coturn", "plugins"):
            src = artifacts_dir() / name
            dst = packages_root / name
            _copy_artifact_payload(src, dst)

        tmp_tar = out_tar.with_suffix(".tmp")
        with tarfile.open(tmp_tar, "w:gz") as tf:
            tf.add(str(root), arcname=bundle_root)

        os.replace(tmp_tar, out_tar)

    return BuildResult(
        bundle_name=tar_name,
        tar_path=out_tar,
        manifest_path=out_tar,
        overlays=overlays,
    )
