from __future__ import annotations

import json
import os
import shutil
import socket
from pathlib import Path

BOOTSTRAP_ROOT = Path("/opt/taks-bootstrap")
NODE_ROOT = Path("/opt/tak/tools/takctl/web/assets/branding/node")
STATE_ROOT = Path("/opt/tak/tools/takctl/state/branding")
STATE_FILE = STATE_ROOT / "imported.json"

TOPLEVEL_COPY_NAMES = {
    "files.json",
    "branding.json",
}

def _get_fqdn() -> str:
    fqdn = os.environ.get("TAKS_FQDN", "").strip()
    if fqdn:
        return fqdn
    try:
        return socket.getfqdn().strip()
    except Exception:
        return ""

def _unit_id_from_fqdn(fqdn: str) -> str:
    fqdn = (fqdn or "").strip().lower()
    if not fqdn:
        raise SystemExit("could not determine fqdn")
    first = fqdn.split(".", 1)[0].strip()
    if not first:
        raise SystemExit(f"invalid fqdn: {fqdn!r}")
    return first

def _cleanup_runtime_outputs() -> None:
    NODE_ROOT.mkdir(parents=True, exist_ok=True)

    for p in NODE_ROOT.glob("unit*.png"):
        if p.is_file():
            p.unlink()

    for name in TOPLEVEL_COPY_NAMES:
        p = NODE_ROOT / name
        if p.exists() and p.is_file():
            p.unlink()

def _copy_materialized_branding(src_dir: Path) -> list[str]:
    copied: list[str] = []

    for p in sorted(src_dir.iterdir()):
        if not p.is_file():
            continue

        name = p.name
        if name == "unit.png" or (name.startswith("unit-parent") and name.endswith(".png")) or name in TOPLEVEL_COPY_NAMES:
            dst = NODE_ROOT / name
            shutil.copy2(p, dst)
            copied.append(str(dst))

    return copied

def import_branding() -> int:
    fqdn = _get_fqdn()
    unit_id = _unit_id_from_fqdn(fqdn)

    src_dir = BOOTSTRAP_ROOT / unit_id / "branding"

    NODE_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    if not src_dir.exists():
        print(f"[bootstrap-branding] no bootstrap branding dir at {src_dir}; nothing to import")
        return 0

    _cleanup_runtime_outputs()
    copied_files = _copy_materialized_branding(src_dir)

    summary = {
        "unit_id": unit_id,
        "fqdn": fqdn,
        "source_dir": str(src_dir),
        "copied_files": copied_files,
    }

    files_json = src_dir / "files.json"
    if files_json.is_file():
        try:
            summary["files"] = json.loads(files_json.read_text(encoding="utf-8"))
        except Exception:
            summary["files_json_error"] = f"failed to parse {files_json}"

    STATE_FILE.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"[bootstrap-branding] imported materialized branding for {unit_id} from {src_dir}")
    for path in copied_files:
        print(f"[bootstrap-branding] copied -> {path}")
    return 0

def main() -> int:
    return import_branding()

if __name__ == "__main__":
    raise SystemExit(main())
