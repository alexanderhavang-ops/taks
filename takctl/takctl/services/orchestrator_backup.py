from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


STATE_ROOT = Path("/opt/tak/tools/takctl/state/orchestrator-node-backups")
NODE_CONF = Path("/opt/tak/tools/takctl/conf.d/node.conf")
SUPPORTED_BUCKETS = (
    "cot_state",
    "certs",
    "config",
    "users",
    "documents",
    "takctl_state",
    "martine_state",
    "replay_state",
)
BACKUP_STATE_ARC_ROOT = "opt/tak/tools/takctl/state/orchestrator-node-backups"


def _parse_simple_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_backup_id(backup_id: str) -> str:
    s = str(backup_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", s):
        raise ValueError(f"invalid backup_id: {backup_id!r}")
    return s


def _node_conf() -> dict[str, str]:
    if not NODE_CONF.exists() or not NODE_CONF.is_file():
        return {}
    try:
        return _parse_simple_kv_text(NODE_CONF.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _node_identity() -> dict[str, str]:
    data = _node_conf()
    hostname = socket.gethostname().strip() or "node"
    unit = str(data.get("unit", "") or "").strip()
    fqdn = str(data.get("fqdn", "") or "").strip()
    return {
        "hostname": hostname,
        "unit": unit,
        "fqdn": fqdn,
    }


def _backup_root(backup_id: str) -> Path:
    return STATE_ROOT / _safe_backup_id(backup_id)


def get_backup_artifact_path(backup_id: str) -> Path:
    p = _backup_root(backup_id) / "backup.tar.gz"
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"backup artifact not found: {backup_id}")
    return p


def get_backup_manifest(backup_id: str) -> dict[str, Any]:
    p = _backup_root(backup_id) / "manifest.json"
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"backup manifest not found: {backup_id}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _ensure_state_root() -> None:
    STATE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_ROOT.chmod(0o700)


def _validate_buckets(buckets: Sequence[str] | None) -> list[str]:
    vals = [str(x or "").strip().lower() for x in (buckets or [])]
    vals = [x for x in vals if x]
    if not vals:
        raise ValueError(f"at least one bucket is required; supported: {', '.join(SUPPORTED_BUCKETS)}")
    out: list[str] = []
    seen: set[str] = set()
    for b in vals:
        if b not in SUPPORTED_BUCKETS:
            raise ValueError(f"unsupported bucket: {b}; supported: {', '.join(SUPPORTED_BUCKETS)}")
        if b not in seen:
            out.append(b)
            seen.add(b)
    return out


HELPER = "/usr/local/libexec/taks-state-backup"


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup_inventory() -> dict[str, Any]:
    return json.loads(_helper("inventory"))


def _helper(operation: str) -> bytes:
    proc = subprocess.run(["sudo", "-n", HELPER, operation], capture_output=True)
    if proc.returncode:
        raise ValueError("backup helper failed: " + proc.stderr.decode("utf-8", errors="replace").strip())
    return proc.stdout


def snapshot_perception_stores():
    # Snapshot actor SQLite stores using SQLite's backup API, never tar a live WAL.
    import sqlite3
    import os
    root=Path('/opt/tak/simulation')
    archive=Path('/opt/tak/tools/takctl/state/simulation-perception')
    for source in root.glob('perception-*.sqlite'):
        if source.is_symlink() or not source.is_file(): continue
        archive.mkdir(parents=True,exist_ok=True)
        target=archive/source.name;temporary=target.with_suffix('.tmp')
        with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as reader, sqlite3.connect(temporary) as writer:
            reader.backup(writer,pages=128)
        os.chmod(temporary,0o600);os.replace(temporary,target)


def _build_bucket(bucket_name: str, stage_dir: Path) -> dict[str, Any]:
    if bucket_name == "takctl_state": snapshot_perception_stores()
    if bucket_name not in SUPPORTED_BUCKETS:
        raise ValueError(f"unsupported bucket: {bucket_name}")
    relative = f"buckets/{bucket_name}." + ("pg_dump" if bucket_name == "cot_state" else "tar.gz")
    dst = stage_dir / relative
    # Stream large CoT dumps directly to disk, rather than retaining them in RAM.
    with dst.open("wb") as output:
        proc = subprocess.run(["sudo", "-n", HELPER, bucket_name], stdout=output, stderr=subprocess.PIPE)
    if proc.returncode:
        raise ValueError("backup helper failed: " + proc.stderr.decode("utf-8", errors="replace").strip())
    return {
        "type": "postgres_custom_dump" if bucket_name == "cot_state" else "paths_tar_gz",
        "bucket_file": relative,
        "restore": "pg_restore_custom" if bucket_name == "cot_state" else "extract_to_root",
        "size_bytes": dst.stat().st_size,
        "sha256": _file_digest(dst),
        **({"ldap_format": "slapcat_ldif"} if bucket_name == "users" else {}),
    }


def create_backup(buckets: Sequence[str] | None) -> dict[str, Any]:
    wanted = _validate_buckets(buckets)
    _ensure_state_root()

    ident = _node_identity()
    stem = ident.get("unit") or ident.get("fqdn") or ident.get("hostname") or "node"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "node"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_id = _safe_backup_id(f"{stamp}-{stem}-{uuid.uuid4().hex[:8]}")

    root = _backup_root(backup_id)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)

    try:
        with tempfile.TemporaryDirectory(prefix=f"{backup_id}-", dir=str(root)) as td:
            stage = Path(td)
            (stage / "buckets").mkdir(parents=True, exist_ok=True)

            manifest: dict[str, Any] = {
                "format_version": 2,
                "inventory": backup_inventory(),
                "backup_id": backup_id,
                "created_at": _now_utc(),
                "node": ident,
                "bucket_order": wanted,
                "buckets": {},
            }

            for bucket_name in wanted:
                manifest["buckets"][bucket_name] = _build_bucket(bucket_name, stage)

            manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
            (stage / "manifest.json").write_text(manifest_text, encoding="utf-8")

            artifact_path = root / "backup.tar.gz"
            artifact_path.touch(mode=0o600)
            with tarfile.open(artifact_path, "w:gz") as tf:
                tf.add(str(stage / "manifest.json"), arcname="manifest.json")
                for p in sorted((stage / "buckets").iterdir()):
                    tf.add(str(p), arcname=f"buckets/{p.name}", recursive=True)

            manifest_path = root / "manifest.json"
            manifest_path.write_text(manifest_text, encoding="utf-8")

        return {
            "backup_id": backup_id,
            "manifest": manifest,
            "artifact_path": str(artifact_path),
            "manifest_path": str(root / "manifest.json"),
            "size_bytes": artifact_path.stat().st_size if artifact_path.exists() else 0,
        }
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
