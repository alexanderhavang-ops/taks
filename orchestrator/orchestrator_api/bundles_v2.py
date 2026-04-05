from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from orchestrator_core.bundles import (
    build_bundle_from_state,
    bundle_readiness,
    rendered_bundles_dir,
)


def bundle_dir() -> Path:
    return rendered_bundles_dir()


def bundle_name_for_unit(unit_path: str) -> str:
    up = str(unit_path or "").strip().strip("/")
    if not up:
        raise ValueError("unit_path is required")
    safe = up.replace("/", "-")
    return f"{safe}.tar.gz"


def resolve_bundle_path(bundle_name: str) -> Path:
    d = rendered_bundles_dir()

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



def get_unit_bundle_readiness(unit_path: str, role: str) -> dict:
    return bundle_readiness(unit_path, role)


def ensure_unit_bundle(unit_path: str, role: str) -> Path:
    bundle_name = bundle_name_for_unit(unit_path)
    built = build_bundle_from_state(
        unit_path=unit_path,
        role=role,
        bundle_name=bundle_name,
    )
    return Path(str(built.get("tar_path") or ""))
