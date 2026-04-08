from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable

BOOTSTRAP_ROOT = Path("/etc/taks-bootstrap.d")
BOOTSTRAP_CONFIG_DIRS = [BOOTSTRAP_ROOT / "config.d", BOOTSTRAP_ROOT / "config"]
BOOTSTRAP_SECRETS_DIRS = [BOOTSTRAP_ROOT / "secrets.d", BOOTSTRAP_ROOT / "secrets"]


def parse_simple_kv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def write_simple_kv(path: Path, data: Dict[str, str], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{k} = {v}" for k, v in data.items()]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(rows) + "\n", encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)


def source_components(src_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    if not src_dir.exists() or not src_dir.is_dir():
        return out
    for src in sorted(src_dir.iterdir()):
        if not src.is_file():
            continue
        name = src.name
        if name.endswith(".conf.template"):
            out[name[:-len(".template")]] = src
        elif name.endswith(".conf"):
            out[name] = src
    return out


def bootstrap_components(src_dirs: Iterable[Path]) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for src_dir in src_dirs:
        if not src_dir.exists() or not src_dir.is_dir():
            continue
        for src in sorted(src_dir.iterdir()):
            if src.is_file() and src.name.endswith(".conf"):
                out[src.name] = src
    return out


def materialize_component_dir_once(*, src_dir: Path, bootstrap_dirs: Iterable[Path], dst_dir: Path, mode: int) -> int:
    src_map = source_components(src_dir)
    bootstrap_map = bootstrap_components(bootstrap_dirs)
    names = sorted(set(src_map.keys()) | set(bootstrap_map.keys()))
    dst_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for name in names:
        dst = dst_dir / name
        if dst.exists():
            continue

        defaults = parse_simple_kv(src_map[name]) if name in src_map else {}
        override = parse_simple_kv(bootstrap_map[name]) if name in bootstrap_map else {}
        merged: Dict[str, str] = {}
        merged.update(defaults)
        merged.update(override)
        if not merged:
            continue
        write_simple_kv(dst, merged, mode)
        created += 1
    return created
