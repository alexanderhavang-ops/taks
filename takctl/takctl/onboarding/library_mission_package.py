from __future__ import annotations

import hashlib
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


LIBRARY_ROOT = Path("/opt/tak/tools/takctl/data/library")
ALLOWED_SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_manifest_uid(subtree: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"taks:library-mission-package:{subtree}"))


def _safe_subtree(subtree: str) -> str:
    value = str(subtree or "").strip().lower()
    if value not in ALLOWED_SUBTREES:
        raise RuntimeError(f"unsupported library subtree: {subtree!r}")
    return value


def _subtree_root(subtree: str) -> Path:
    return LIBRARY_ROOT / _safe_subtree(subtree)


def _collect_files(subtree: str) -> list[dict[str, Any]]:
    root = _subtree_root(subtree)
    if not root.exists():
        return []

    out: list[dict[str, Any]] = []
    for src in sorted(root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(root)
        if any(str(part).startswith(".") for part in rel.parts):
            continue
        rel_s = rel.as_posix()
        if not rel_s:
            continue
        out.append(
            {
                "source_path": str(src),
                "relpath": rel_s,
                "zip_entry": f"{subtree}/{rel_s}",
                "size_bytes": src.stat().st_size,
                "sha256": _sha256_file(src),
            }
        )
    return out


def _render_manifest_xml(*, manifest_uid: str, display_filename: str, files: list[dict[str, Any]]) -> str:
    lines = [
        '<MissionPackageManifest version="2">',
        "  <Configuration>",
        f'    <Parameter name="uid" value="{escape(manifest_uid)}"/>',
        f'    <Parameter name="name" value="{escape(display_filename)}"/>',
        '    <Parameter name="onReceiveImport" value="true"/>',
        '    <Parameter name="onReceiveDelete" value="false"/>',
        "  </Configuration>",
        "  <Contents>",
    ]
    for item in files:
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


def write_library_mission_package(
    out_zip: Path,
    *,
    subtree: str,
    display_name: str = "",
    display_filename: str = "",
) -> dict[str, Any]:
    subtree = _safe_subtree(subtree)
    files = _collect_files(subtree)
    if not files:
        raise RuntimeError(f"library subtree is empty: {_subtree_root(subtree)}")

    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    manifest_uid = _stable_manifest_uid(subtree)
    final_display_name = str(display_name or f"ATAK library {subtree}").strip()
    final_display_filename = str(display_filename or f"ATAK-library-{subtree}.zip").strip()
    if not final_display_filename.lower().endswith(".zip"):
        final_display_filename += ".zip"

    manifest_xml = _render_manifest_xml(
        manifest_uid=manifest_uid,
        display_filename=final_display_filename,
        files=files,
    )

    with zipfile.ZipFile(
        out_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as zf:
        zf.writestr("MANIFEST/manifest.xml", manifest_xml)
        for item in files:
            zf.write(item["source_path"], arcname=item["zip_entry"])

    return {
        "ok": True,
        "kind": "library_mission_package",
        "subtree": subtree,
        "title": final_display_name,
        "display_name": final_display_name,
        "display_filename": final_display_filename,
        "manifest_uid": manifest_uid,
        "library_root": str(_subtree_root(subtree)),
        "artifact_path": str(out_zip),
        "generated_at": _utc_now().isoformat(),
        "files": [
            {
                "relpath": str(item["relpath"]),
                "zip_entry": str(item["zip_entry"]),
                "size_bytes": int(item["size_bytes"]),
                "sha256": str(item["sha256"]),
            }
            for item in files
        ],
    }
