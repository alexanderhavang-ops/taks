# orchestrator/orchestrator_api/bundles_v2.py
from __future__ import annotations

import hashlib
import inspect
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Tuple

from fastapi import HTTPException

from orchestrator_core.bundles import (
    build_bundle_from_state,
    bundles_dir,
    default_bundle_dir,
    role_bundle_overlay_dir,
    unit_bundle_overlay_dir,
)

STATIC_BUNDLE_NAME = "taks_orch_bundle.tar.gz"


def bundle_dir() -> Path:
    return Path(os.environ.get("TAKS_BUNDLE_DIR") or "/opt/tak-orch/state/bundles")


def resolve_bundle_path(bundle_name: str) -> Path:
    d = bundle_dir()
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


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ts_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _iter_files(root: Path) -> Iterable[Tuple[str, int, int]]:
    """
    Return tuples of (relative_path, size, mtime_ns) for all regular files under root.
    """
    if not root.exists():
        return []
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        st = p.stat()
        out.append((str(p.relative_to(root)), int(st.st_size), int(st.st_mtime_ns)))
    return out


def _overlay_fingerprint(unit_path: str, role: str) -> str:
    """
    Fingerprint default + role + unit overlay trees so we can rebuild the static tar
    when overlay content changes.
    """
    h = hashlib.sha256()

    def _add_tree(tag: str, root: Path) -> None:
        h.update(tag.encode("utf-8") + b"\n")
        h.update(str(root).encode("utf-8") + b"\n")
        h.update(b"exists=1\n" if root.exists() else b"exists=0\n")
        for rel, size, mtime_ns in _iter_files(root):
            h.update(rel.encode("utf-8") + b"\n")
            h.update(f"{size}\n".encode("utf-8"))
            h.update(f"{mtime_ns}\n".encode("utf-8"))

    _add_tree("default", default_bundle_dir())
    _add_tree("role", role_bundle_overlay_dir(role))
    _add_tree("unit", unit_bundle_overlay_dir(unit_path))

    return h.hexdigest()


def ensure_static_bundle(unit_path: str, role: str) -> Path:
    """
    Ensure a stable bundle file exists at:

      /opt/tak-orch/state/bundles/taks_orch_bundle.tar.gz

    Rebuild when overlay fingerprint changes (default + role + unit).
    """
    d = bundle_dir()
    d.mkdir(parents=True, exist_ok=True)

    wanted = d / STATIC_BUNDLE_NAME
    stamp = d / (STATIC_BUNDLE_NAME + ".fingerprint")

    fp = _overlay_fingerprint(unit_path=unit_path, role=role)

    if wanted.exists() and stamp.exists():
        old = stamp.read_text(encoding="utf-8").strip()
        if old == fp:
            return wanted

    sig = inspect.signature(build_bundle_from_state)
    params = sig.parameters

    built: Any = None

    # Try safest variants (signature drift across iterations)
    if "bundle_name" in params:
        built = build_bundle_from_state(
            unit_path=unit_path,
            role=role,
            bundle_name=STATIC_BUNDLE_NAME,
        )
    else:
        try:
            built = build_bundle_from_state(unit_path, role, STATIC_BUNDLE_NAME)
        except TypeError:
            built = build_bundle_from_state(unit_path, role)

    # Resolve produced tarball
    tar_path = None
    bundle_name = None

    if hasattr(built, "tar_path"):
        tar_path = Path(getattr(built, "tar_path"))
    if hasattr(built, "bundle_name"):
        bundle_name = str(getattr(built, "bundle_name"))

    if tar_path and tar_path.exists():
        src = tar_path
    elif bundle_name:
        src = bundles_dir() / bundle_name
    else:
        raise RuntimeError("Bundle build did not produce a tarball")

    if not src.exists():
        raise RuntimeError(f"Bundle tarball missing after build: {src}")

    tmp_tar = wanted.with_suffix(".tmp")
    tmp_fp = stamp.with_suffix(".tmp")

    shutil.copyfile(src, tmp_tar)
    tmp_fp.write_text(fp + "\n", encoding="utf-8")

    os.replace(tmp_tar, wanted)
    os.replace(tmp_fp, stamp)

    return wanted
