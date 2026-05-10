from __future__ import annotations

import json
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

from takctl.config import load_config, load_secrets
from takctl.services.userauth_file import auth_file_path

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
    STATE_ROOT.mkdir(parents=True, exist_ok=True)


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


def _unique_existing_paths(paths: Sequence[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        p = Path(raw)
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists():
            out.append(p)
    return out


def _tar_paths(dst: Path, paths: Sequence[Path], *, exclude_arc_roots: Sequence[str] = ()) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    existing = [Path(x) for x in paths if Path(x).exists()]
    if not existing:
        with tarfile.open(dst, "w:gz"):
            return

    cmd = ["sudo", "-n", "tar", "-czf", str(dst), "-C", "/"]

    for root in exclude_arc_roots:
        r = str(root or "").strip("/").strip()
        if r:
            cmd.extend(["--exclude", r, "--exclude", r + "/*"])

    for x in existing:
        cmd.append(str(x).lstrip("/"))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise ValueError(f"tar failed: {msg or proc.returncode}")


def _build_paths_bucket(
    bucket_name: str,
    stage_dir: Path,
    paths: Sequence[Path],
    *,
    exclude_arc_roots: Sequence[str] = (),
) -> dict[str, Any]:
    src_paths = _unique_existing_paths(paths)
    dst = stage_dir / "buckets" / f"{bucket_name}.tar.gz"
    _tar_paths(dst, src_paths, exclude_arc_roots=exclude_arc_roots)
    return {
        "type": "paths_tar_gz",
        "bucket_file": f"buckets/{bucket_name}.tar.gz",
        "restore": "extract_to_root",
        "source_paths": [str(p) for p in src_paths],
        "size_bytes": dst.stat().st_size if dst.exists() else 0,
    }


def _certs_paths() -> list[Path]:
    return [Path("/opt/tak/certs")]



def _users_paths() -> list[Path]:
    out: list[Path] = []
    try:
        cfg = load_config()
        core = str(cfg.get("coreconfig_path", "") or "").strip()
        if core:
            out.append(Path(auth_file_path(core)))
    except Exception:
        pass

    out.extend([
        Path("/opt/tak/UserAuthenticationFile.xml"),
        Path("/etc/taks/ldap.conf"),
        Path("/etc/taks/ldap-secrets.conf"),
        Path("/etc/ldap"),
        Path("/var/lib/ldap"),
    ])
    return out


def _config_paths() -> list[Path]:
    return [
        Path("/opt/tak/CoreConfig.xml"),
        Path("/opt/tak/core"),
        Path("/etc/taks-bootstrap.d/config.d"),
        Path("/etc/taks-bootstrap.d/secrets.d"),
        Path("/opt/tak/tools/takctl/conf.d"),
        Path("/opt/tak/tools/takctl/secrets.d"),
        Path("/opt/tak/tools/takctl/confmeta"),
    ]

def _documents_paths() -> list[Path]:
    return [
        Path("/opt/tak/Documents"),
        Path("/opt/tak/documents"),
        Path("/opt/tak/tools/takctl/state/docs"),
    ]


def _takctl_state_paths() -> list[Path]:
    # Keep takctl-owned operational state, but exclude bulky/rebuildable docs and transient LLM/cache data.
    return [Path("/opt/tak/tools/takctl/state")]


def _martine_state_paths() -> list[Path]:
    # Martine runtime is mostly stateless/rebuildable. Preserve only its TAK identity/certs.
    return [
        Path("/opt/tak/tools/martine/runtime/identity"),
    ]


def _replay_state_paths() -> list[Path]:
    return [Path("/opt/tak/replay")]


def _build_cot_state_bucket(stage_dir: Path) -> dict[str, Any]:
    cfg = load_config()
    sec = load_secrets()

    db_mode = str(cfg.get("db_mode", "") or "").strip().lower()
    db_name = str(cfg.get("db_name", "") or "cot").strip() or "cot"
    db_host = str(cfg.get("db_host", "") or "127.0.0.1").strip() or "127.0.0.1"
    db_port = str(cfg.get("db_port", "") or "5432").strip() or "5432"
    db_user = str(sec.get("db_user", "") or cfg.get("db_user", "") or "cot").strip() or "cot"
    sudo_user = str(cfg.get("sudo_user", "") or "postgres").strip() or "postgres"

    dst = stage_dir / "buckets" / "cot_state.pg_dump"
    dst.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    password = str(sec.get("db_password", "") or "").strip()
    if password:
        env["PGPASSWORD"] = password

    # Use local postgres for full-fidelity backups, but stream to stdout so
    # postgres does not need write permission inside takctl's state directory.
    cmd = ["sudo", "-n", "-u", sudo_user, "pg_dump", "-Fc", db_name]

    proc = subprocess.run(cmd, env=env, capture_output=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        if not msg:
            msg = f"pg_dump failed with exit code {proc.returncode}"
        raise ValueError(f"cot_state backup failed: {msg}")

    dst.write_bytes(proc.stdout or b"")

    return {
        "type": "postgres_custom_dump",
        "bucket_file": "buckets/cot_state.pg_dump",
        "restore": "pg_restore_custom",
        "db": {
            "mode": db_mode or "direct",
            "db_name": db_name,
            "db_host": db_host,
            "db_port": db_port,
            "db_user": db_user,
            "sudo_user": sudo_user,
        },
        "size_bytes": dst.stat().st_size if dst.exists() else 0,
    }



def _build_bucket(bucket_name: str, stage_dir: Path) -> dict[str, Any]:
    if bucket_name == "cot_state":
        return _build_cot_state_bucket(stage_dir)
    if bucket_name == "certs":
        return _build_paths_bucket(bucket_name, stage_dir, _certs_paths())
    if bucket_name == "config":
        return _build_paths_bucket(bucket_name, stage_dir, _config_paths())
    if bucket_name == "users":
        return _build_paths_bucket(bucket_name, stage_dir, _users_paths())
    if bucket_name == "documents":
        return _build_paths_bucket(bucket_name, stage_dir, _documents_paths())
    if bucket_name == "takctl_state":
        return _build_paths_bucket(
            bucket_name,
            stage_dir,
            _takctl_state_paths(),
            exclude_arc_roots=[
                BACKUP_STATE_ARC_ROOT,
                "opt/tak/tools/takctl/state/docs",
                "opt/tak/tools/takctl/state/llm_usage.jsonl",
                "opt/tak/tools/takctl/state/llm2",
                "opt/tak/tools/takctl/state/llm3",
            ],
        )
    if bucket_name == "martine_state":
        return _build_paths_bucket(bucket_name, stage_dir, _martine_state_paths())
    if bucket_name == "replay_state":
        return _build_paths_bucket(bucket_name, stage_dir, _replay_state_paths())
    raise ValueError(f"unsupported bucket: {bucket_name}")

def create_backup(buckets: Sequence[str] | None) -> dict[str, Any]:
    wanted = _validate_buckets(buckets)
    _ensure_state_root()

    ident = _node_identity()
    stem = ident.get("unit_path") or ident.get("node_fqdn") or ident.get("hostname") or "node"
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "node"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_id = _safe_backup_id(f"{stamp}-{stem}-{uuid.uuid4().hex[:8]}")

    root = _backup_root(backup_id)
    root.mkdir(parents=True, exist_ok=False)

    try:
        with tempfile.TemporaryDirectory(prefix=f"{backup_id}-", dir=str(root)) as td:
            stage = Path(td)
            (stage / "buckets").mkdir(parents=True, exist_ok=True)

            manifest: dict[str, Any] = {
                "format_version": 1,
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
