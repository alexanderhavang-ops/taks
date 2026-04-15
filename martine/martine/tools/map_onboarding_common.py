from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


_ALLOWED_SOURCE_SUFFIXES = (".mbtiles", ".mbtiles_")
_PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ts() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(data), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalize_package_id(package_id: str) -> str:
    value = (package_id or "").strip()
    if not value:
        raise RuntimeError("package_id is required")
    if not _PACKAGE_ID_RE.fullmatch(value):
        raise RuntimeError(
            "invalid package_id; expected lowercase [a-z0-9._-], 1..128 chars"
        )
    return value


def _safe_filename_token(text: str, fallback: str) -> str:
    s = str(text or "").strip()
    s = _SAFE_FILENAME_RE.sub("-", s)
    s = re.sub(r"\s+", "-", s).strip("-. ")
    return s or fallback


def _stable_manifest_uid(package_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"taks:map-onboarding:{package_id}"))


def default_map_library_dir() -> Path:
    env = os.environ.get("TAKS_MAP_LIBRARY_DIR", "").strip()
    if env:
        return Path(env)
    return Path("/opt/tak/tools/takctl/data/library/maps")


def default_state_root() -> Path:
    env = os.environ.get("TAKS_MAP_ONBOARDING_STATE_ROOT", "").strip()
    if env:
        return Path(env)

    candidates = [
        Path("/opt/tak/tools/martine/state/map_onboarding"),
        Path("/opt/taks/martine/state/map_onboarding"),
    ]
    for p in candidates:
        if p.parent.exists():
            return p
    return candidates[0]


def _normalized_arcname(src: Path) -> str:
    name = src.name
    if name.endswith(".mbtiles_"):
        return name[:-1]
    return name


def _iter_library_map_files(library_dir: Path) -> list[Path]:
    if not library_dir.exists():
        raise RuntimeError(f"map library dir not found: {library_dir}")
    if not library_dir.is_dir():
        raise RuntimeError(f"map library path is not a directory: {library_dir}")

    out: list[Path] = []
    for p in sorted(library_dir.iterdir()):
        if not p.is_file():
            continue
        suffix = p.suffix.lower()
        if suffix in _ALLOWED_SOURCE_SUFFIXES:
            out.append(p)

    if not out:
        raise RuntimeError(
            f"no supported map files found in {library_dir} "
            f"(supported: {', '.join(_ALLOWED_SOURCE_SUFFIXES)})"
        )
    return out


def resolve_package(
    *,
    package_id: str,
    library_dir: Path | None = None,
) -> dict[str, Any]:
    package_id = _normalize_package_id(package_id)
    lib = (library_dir or default_map_library_dir()).resolve()
    src_files = _iter_library_map_files(lib)

    resolved_files: list[dict[str, Any]] = []
    for src in src_files:
        arcname = _normalized_arcname(src)
        if not arcname.lower().endswith(".mbtiles"):
            raise RuntimeError(f"normalized arcname must end with .mbtiles: {arcname}")

        resolved_files.append(
            {
                "type": "mbtiles",
                "source_path": str(src),
                "arcname": arcname,
                "zip_entry": f"Imagery/{arcname}",
                "size_bytes": src.stat().st_size,
                "sha256": _sha256_file(src),
            }
        )

    display_name = f"ATAK maps {package_id}"
    display_filename = f"{_safe_filename_token(display_name, package_id)}.zip"

    return {
        "package_id": package_id,
        "title": display_name,
        "version": _utc_now().strftime("%Y.%m.%d"),
        "description": f"Offline map package from {lib}",
        "manifest_uid": _stable_manifest_uid(package_id),
        "display_name": display_name,
        "display_filename": display_filename,
        "library_dir": str(lib),
        "on_receive_import": True,
        "on_receive_delete": False,
        "files": resolved_files,
    }


def _render_manifest_xml(package: dict[str, Any]) -> str:
    lines = [
        '<MissionPackageManifest version="2">',
        "  <Configuration>",
        f'    <Parameter name="uid" value="{escape(str(package["manifest_uid"]))}"/>',
        f'    <Parameter name="name" value="{escape(str(package["display_filename"]))}"/>',
        f'    <Parameter name="onReceiveImport" value="{"true" if package["on_receive_import"] else "false"}"/>',
        f'    <Parameter name="onReceiveDelete" value="{"true" if package["on_receive_delete"] else "false"}"/>',
        "  </Configuration>",
        "  <Contents>",
    ]
    for item in package["files"]:
        lines.append(
            f'    <Content ignore="false" zipEntry="{escape(str(item["zip_entry"]))}"/>'
        )
    lines.extend(
        [
            "  </Contents>",
            "</MissionPackageManifest>",
            "",
        ]
    )
    return "\n".join(lines)


def build_map_package(
    *,
    package_id: str = "maps-basic",
    requested_by: str = "",
    library_dir: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    package = resolve_package(package_id=package_id, library_dir=library_dir)

    root = _mkdir(state_root or default_state_root())
    run_id = f"map-onboarding-{_ts()}-{uuid.uuid4().hex[:8]}"
    run_dir = _mkdir(root / run_id)
    artifacts_dir = _mkdir(run_dir / "artifacts")

    manifest_xml = _render_manifest_xml(package)
    package_zip = artifacts_dir / package["display_filename"]

    with zipfile.ZipFile(
        package_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        zf.writestr("MANIFEST/manifest.xml", manifest_xml)
        for item in package["files"]:
            zf.write(item["source_path"], arcname=item["zip_entry"])

    manifest_json = {
        "kind": "map_pack",
        "package_id": package["package_id"],
        "title": package["title"],
        "version": package["version"],
        "description": package["description"],
        "generated_at": _utc_now().isoformat(),
        "requested_by": requested_by,
        "manifest_uid": package["manifest_uid"],
        "display_name": package["display_name"],
        "display_filename": package["display_filename"],
        "library_dir": package["library_dir"],
        "on_receive_import": package["on_receive_import"],
        "on_receive_delete": package["on_receive_delete"],
        "files": [
            {
                "type": item["type"],
                "arcname": item["arcname"],
                "zip_entry": item["zip_entry"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in package["files"]
        ],
    }

    result = {
        "ok": True,
        "run_id": run_id,
        "kind": "map_pack",
        "package_id": package["package_id"],
        "title": package["title"],
        "version": package["version"],
        "requested_by": requested_by,
        "library_dir": package["library_dir"],
        "run_dir": str(run_dir),
        "manifest_uid": package["manifest_uid"],
        "display_name": package["display_name"],
        "display_filename": package["display_filename"],
        "on_receive_import": package["on_receive_import"],
        "on_receive_delete": package["on_receive_delete"],
        "artifacts": {
            "package_zip": str(package_zip),
            "manifest_xml_path": str(run_dir / "manifest.xml"),
            "manifest_xml_path_in_zip": "MANIFEST/manifest.xml",
        },
        "files": manifest_json["files"],
        "generated_at": manifest_json["generated_at"],
    }

    _write_json(
        run_dir / "request.json",
        {
            "package_id": package_id,
            "requested_by": requested_by,
            "library_dir": package["library_dir"],
            "state_root": str(root),
            "generated_at": manifest_json["generated_at"],
        },
    )
    _write_json(run_dir / "manifest.json", manifest_json)
    _write_text(run_dir / "manifest.xml", manifest_xml)
    _write_json(run_dir / "result.json", result)

    return result


def _cmd_resolve(args: argparse.Namespace) -> int:
    result = resolve_package(
        package_id=args.package_id,
        library_dir=Path(args.library_dir) if args.library_dir else None,
    )
    sys.stdout.write(_json_dumps(result))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    result = build_map_package(
        package_id=args.package_id,
        requested_by=args.requested_by or "",
        library_dir=Path(args.library_dir) if args.library_dir else None,
        state_root=Path(args.state_root) if args.state_root else None,
    )
    sys.stdout.write(_json_dumps(result))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build ATAK offline map mission packages from the TAKS map library."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve map files from library")
    p_resolve.add_argument("--package-id", default="maps-basic")
    p_resolve.add_argument("--library-dir", default="")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_build = sub.add_parser("build", help="Build offline map package zip + state files")
    p_build.add_argument("--package-id", default="maps-basic")
    p_build.add_argument("--requested-by", default="")
    p_build.add_argument("--library-dir", default="")
    p_build.add_argument("--state-root", default="")
    p_build.set_defaults(func=_cmd_build)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except RuntimeError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
