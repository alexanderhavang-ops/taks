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


_ALLOWED_FILE_TYPES = {"apk", "zip", "file"}
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


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _path_has_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    for p in path.rglob("*"):
        if p.is_file():
            return True
    return False


def default_registry_path() -> Path:
    env = os.environ.get("TAKS_PLUGIN_ONBOARDING_REGISTRY", "").strip()
    if env:
        return Path(env)

    candidates = [
        Path("/opt/tak/tools/martine/plugin_onboarding_registry.json"),
        Path("/opt/taks/martine/martine/tools/plugin_onboarding_registry.json"),
    ]
    existing = _first_existing(candidates)
    return existing if existing is not None else candidates[-1]


def default_state_root() -> Path:
    env = os.environ.get("TAKS_PLUGIN_ONBOARDING_STATE_ROOT", "").strip()
    if env:
        return Path(env)

    candidates = [
        Path("/opt/tak/tools/martine/state/plugin_onboarding"),
        Path("/opt/taks/martine/state/plugin_onboarding"),
    ]
    existing_parent = _first_existing([p.parent for p in candidates if p.parent.exists()])
    if existing_parent is not None:
        if existing_parent == candidates[0].parent:
            return candidates[0]
        if existing_parent == candidates[1].parent:
            return candidates[1]
    return candidates[0]


def default_plugin_library_dir() -> Path:
    env = os.environ.get("TAKS_PLUGIN_ONBOARDING_LIBRARY_DIR", "").strip()
    if env:
        return Path(env)

    candidates = [
        Path("/opt/tak/tools/takctl/data/library/plugins"),
        Path("/opt/tak/tools/takctl/plugins"),
    ]

    for p in candidates:
        if _path_has_files(p):
            return p

    existing = _first_existing(candidates)
    return existing if existing is not None else candidates[0]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise RuntimeError(f"registry file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"invalid json in registry file {path}: {e}") from e


def _write_json(path: Path, data: Any) -> None:
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
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"taks:plugin-onboarding:{package_id}"))


def _friendly_display_filename(raw: dict[str, Any], title: str, package_id: str) -> str:
    explicit = str(raw.get("filename") or "").strip()
    if explicit:
        return explicit if explicit.lower().endswith(".zip") else explicit + ".zip"
    base = _safe_filename_token(title or package_id, package_id)
    return f"{base}.zip"


def load_registry(registry_path: Path | None = None) -> dict[str, Any]:
    path = registry_path or default_registry_path()
    data = _load_json(path)

    if not isinstance(data, dict):
        raise RuntimeError(f"registry must be a json object: {path}")

    packages = data.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError(f"registry must contain object key 'packages': {path}")

    return {
        "registry_path": str(path),
        "packages": packages,
    }


def _file_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".apk":
        return "apk"
    if ext == ".zip":
        return "zip"
    return "file"


def _resolve_plugins_basic_from_library(package_id: str) -> dict[str, Any] | None:
    if package_id != "plugins-basic":
        return None

    library_dir = default_plugin_library_dir()
    if not library_dir.exists():
        return None

    resolved_files: list[dict[str, Any]] = []
    for src in sorted(library_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(library_dir)
        if any(str(part).startswith(".") for part in rel.parts):
            continue
        arcname = rel.as_posix()
        if not arcname:
            continue
        resolved_files.append(
            {
                "type": _file_type_for_path(src),
                "source_path": str(src),
                "arcname": arcname,
                "zip_entry": f"plugins/{arcname}",
                "size_bytes": src.stat().st_size,
                "sha256": _sha256_file(src),
            }
        )

    if not resolved_files:
        return None

    display_name = "ATAK plugins basic"
    display_filename = "ATAK-plugins-basic.zip"

    return {
        "package_id": package_id,
        "title": display_name,
        "version": _utc_now().strftime("%Y.%m.%d"),
        "description": f"Dynamic plugin pack from {library_dir}",
        "atak_min_version": "",
        "requires_user_install_confirmation": True,
        "on_receive_import": True,
        "on_receive_delete": False,
        "manifest_uid": _stable_manifest_uid(package_id),
        "display_name": display_name,
        "display_filename": display_filename,
        "registry_path": f"dynamic:{library_dir}",
        "files": resolved_files,
        "raw": {
            "title": display_name,
            "filename": display_filename,
            "source": "library",
            "library_dir": str(library_dir),
        },
    }


def resolve_package(
    package_id: str,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    package_id = _normalize_package_id(package_id)

    dynamic = _resolve_plugins_basic_from_library(package_id)
    if dynamic is not None:
        return dynamic

    reg = load_registry(registry_path=registry_path)
    packages = reg["packages"]
    raw = packages.get(package_id)

    if raw is None:
        known = ", ".join(sorted(packages.keys())) or "<none>"
        raise RuntimeError(
            f"package_id not found in registry: {package_id}. known packages: {known}"
        )
    if not isinstance(raw, dict):
        raise RuntimeError(f"registry entry for {package_id} must be an object")

    title = str(raw.get("title") or package_id).strip()
    version = str(raw.get("version") or "").strip()
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError(f"registry entry for {package_id} must have non-empty 'files'")

    registry_file = Path(reg["registry_path"])
    resolved_files: list[dict[str, Any]] = []

    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            raise RuntimeError(f"{package_id}: files[{idx}] must be an object")

        ftype = str(item.get("type") or "file").strip()
        if ftype not in _ALLOWED_FILE_TYPES:
            raise RuntimeError(
                f"{package_id}: files[{idx}].type must be one of {sorted(_ALLOWED_FILE_TYPES)}"
            )

        src_raw = str(item.get("path") or "").strip()
        if not src_raw:
            raise RuntimeError(f"{package_id}: files[{idx}].path is required")

        src = Path(src_raw)
        if not src.is_absolute():
            src = (registry_file.parent / src).resolve()

        arcname = str(item.get("arcname") or src.name).strip()
        if not arcname:
            raise RuntimeError(f"{package_id}: files[{idx}].arcname resolved to empty")

        if arcname.startswith("/") or ".." in Path(arcname).parts:
            raise RuntimeError(f"{package_id}: illegal arcname for files[{idx}]: {arcname}")

        if not src.exists():
            raise RuntimeError(f"{package_id}: source file missing: {src}")
        if not src.is_file():
            raise RuntimeError(f"{package_id}: source path is not a file: {src}")

        resolved_files.append(
            {
                "type": ftype,
                "source_path": str(src),
                "arcname": arcname,
                "zip_entry": f"plugins/{arcname}",
                "size_bytes": src.stat().st_size,
                "sha256": _sha256_file(src),
            }
        )

    manifest_uid = str(raw.get("uid") or "").strip() or _stable_manifest_uid(package_id)
    display_name = str(raw.get("display_name") or title).strip() or title or package_id
    display_filename = _friendly_display_filename(raw, display_name, package_id)

    return {
        "package_id": package_id,
        "title": title,
        "version": version,
        "description": str(raw.get("description") or "").strip(),
        "atak_min_version": str(raw.get("atak_min_version") or "").strip(),
        "requires_user_install_confirmation": bool(
            raw.get("requires_user_install_confirmation", True)
        ),
        "on_receive_import": bool(raw.get("on_receive_import", True)),
        "on_receive_delete": bool(raw.get("on_receive_delete", False)),
        "manifest_uid": manifest_uid,
        "display_name": display_name,
        "display_filename": display_filename,
        "registry_path": str(registry_file),
        "files": resolved_files,
        "raw": raw,
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


def build_plugin_package(
    *,
    package_id: str,
    requested_by: str = "",
    registry_path: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    package = resolve_package(package_id=package_id, registry_path=registry_path)

    root = _mkdir(state_root or default_state_root())
    run_id = f"plugin-onboarding-{_ts()}-{uuid.uuid4().hex[:8]}"
    run_dir = _mkdir(root / run_id)
    artifacts_dir = _mkdir(run_dir / "artifacts")

    manifest_xml = _render_manifest_xml(package)
    manifest_json = {
        "kind": "plugin_pack",
        "package_id": package["package_id"],
        "title": package["title"],
        "version": package["version"],
        "description": package["description"],
        "atak_min_version": package["atak_min_version"],
        "requires_user_install_confirmation": package["requires_user_install_confirmation"],
        "generated_at": _utc_now().isoformat(),
        "requested_by": requested_by,
        "manifest_uid": package["manifest_uid"],
        "display_name": package["display_name"],
        "display_filename": package["display_filename"],
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

    _write_json(run_dir / "request.json", {
        "package_id": package_id,
        "requested_by": requested_by,
        "registry_path": package["registry_path"],
        "state_root": str(root),
        "generated_at": manifest_json["generated_at"],
    })
    _write_json(run_dir / "manifest.json", manifest_json)
    _write_text(run_dir / "manifest.xml", manifest_xml)

    result = {
        "ok": True,
        "run_id": run_id,
        "kind": "plugin_pack",
        "package_id": package["package_id"],
        "title": package["title"],
        "version": package["version"],
        "requested_by": requested_by,
        "registry_path": package["registry_path"],
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

    _write_json(run_dir / "result.json", result)
    return result


def _cmd_build(args: argparse.Namespace) -> int:
    result = build_plugin_package(
        package_id=args.package_id,
        requested_by=args.requested_by or "",
        registry_path=Path(args.registry_path) if args.registry_path else None,
        state_root=Path(args.state_root) if args.state_root else None,
    )
    sys.stdout.write(_json_dumps(result))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    result = resolve_package(
        package_id=args.package_id,
        registry_path=Path(args.registry_path) if args.registry_path else None,
    )
    sys.stdout.write(_json_dumps(result))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build ATAK plugin onboarding packages with MANIFEST/manifest.xml."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="Resolve and validate one package entry")
    p_resolve.add_argument("--package-id", required=True)
    p_resolve.add_argument("--registry-path", default="")
    p_resolve.set_defaults(func=_cmd_resolve)

    p_build = sub.add_parser("build", help="Build plugin package zip + state files")
    p_build.add_argument("--package-id", required=True)
    p_build.add_argument("--requested-by", default="")
    p_build.add_argument("--registry-path", default="")
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
