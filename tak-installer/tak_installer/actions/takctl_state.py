from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)

STATE_ROOT = Path("/opt/tak/takctl-state")
APPLY_JSON = STATE_ROOT / "apply.json"

BOOTSTRAP_ROOT = Path("/opt/taks-bootstrap")
BOOTSTRAP_NODE_CONF = Path("/etc/taks-bootstrap.d/config.d/node.conf")

RUNTIME_LIBRARY_ROOT = Path("/opt/tak/tools/takctl/data/library")
LIBRARY_SUBTREES = (
    "packages",
    "branding",
    "users",
    "plugins",
    "maps",
    "missions",
    "documents",
    "misc",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_apply_token(ctx: Context) -> str:
    ts = _utc_now_iso()
    payload = {"apply_ts_utc": ts}
    tmp = APPLY_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(APPLY_JSON)
    log.info("takctl-state: wrote apply token %s -> %s", ts, APPLY_JSON)
    return ts


def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = str(k or "").strip()
        val = str(v or "").strip()
        if key:
            out[key] = val
    return out


def _unit_id_from_fqdn(raw: str) -> str:
    fqdn = str(raw or "").strip().lower()
    if not fqdn:
        return ""
    host = fqdn.split(".", 1)[0].strip()
    return host


def _bootstrap_unit_dir() -> Path | None:
    rows = _read_simple_kv(BOOTSTRAP_NODE_CONF)

    for key in ("node_fqdn", "fqdn"):
        unit_id = _unit_id_from_fqdn(rows.get(key, ""))
        if unit_id:
            cand = BOOTSTRAP_ROOT / unit_id
            if cand.is_dir():
                return cand

    if not BOOTSTRAP_ROOT.exists():
        return None

    dirs = sorted(p for p in BOOTSTRAP_ROOT.iterdir() if p.is_dir())
    if len(dirs) == 1:
        return dirs[0]

    for d in dirs:
        if any((d / name).exists() for name in LIBRARY_SUBTREES):
            return d

    return None


def _copy_tree_merge(src_dir: Path, dst_dir: Path) -> int:
    if not src_dir.is_dir():
        return 0

    copied = 0
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        dst = dst_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def _ensure_library_dirs() -> None:
    for name in LIBRARY_SUBTREES:
        (RUNTIME_LIBRARY_ROOT / name).mkdir(parents=True, exist_ok=True)


def _seed_library_from_bootstrap() -> None:
    _ensure_library_dirs()

    src_root = _bootstrap_unit_dir()
    if src_root is None:
        log.info("takctl-state: no bootstrap unit dir found under %s; library seed skipped", BOOTSTRAP_ROOT)
        return

    summary: dict[str, int] = {}
    for name in LIBRARY_SUBTREES:
        src_dir = src_root / name
        dst_dir = RUNTIME_LIBRARY_ROOT / name
        summary[name] = _copy_tree_merge(src_dir, dst_dir)

    log.info("takctl-state: library seeded from %s -> %s summary=%s", src_root, RUNTIME_LIBRARY_ROOT, summary)


def _fix_state_perms() -> None:
    subprocess.run(["chown", "-R", "tak:tak", str(STATE_ROOT)], check=False)
    subprocess.run(
        ["bash", "-lc", f'find "{STATE_ROOT}" -type d -exec chmod 2770 {{}} \\; 2>/dev/null || true'],
        check=False,
    )
    subprocess.run(
        ["bash", "-lc", f'find "{STATE_ROOT}" -type f -exec chmod 0660 {{}} \\; 2>/dev/null || true'],
        check=False,
    )


def _fix_library_perms() -> None:
    if not RUNTIME_LIBRARY_ROOT.exists():
        return
    subprocess.run(["chown", "-R", "tak:tak", str(RUNTIME_LIBRARY_ROOT)], check=False)
    subprocess.run(
        ["bash", "-lc", f'find "{RUNTIME_LIBRARY_ROOT}" -type d -exec chmod 2770 {{}} \\; 2>/dev/null || true'],
        check=False,
    )
    subprocess.run(
        ["bash", "-lc", f'find "{RUNTIME_LIBRARY_ROOT}" -type f -exec chmod 0660 {{}} \\; 2>/dev/null || true'],
        check=False,
    )


@dataclass
class TakctlStateAction:
    """
    Ensures installer-owned runtime state directories exist.
    """

    def inspect(self, ctx: Context) -> int:
        return 0

    def apply(self, ctx: Context) -> int:
        log.info("takctl-state: ensuring runtime state directories exist")

        STATE_ROOT.mkdir(parents=True, exist_ok=True)

        (STATE_ROOT / "onboarding" / "users").mkdir(parents=True, exist_ok=True)
        (STATE_ROOT / "onboarding" / "identities").mkdir(parents=True, exist_ok=True)

        (STATE_ROOT / "policies.d").mkdir(parents=True, exist_ok=True)

        _ensure_library_dirs()
        _seed_library_from_bootstrap()

        _fix_state_perms()
        _fix_library_perms()

        _write_apply_token(ctx)

        _fix_state_perms()
        _fix_library_perms()

        log.info("takctl-state: ready")
        return 0


class _Wrapper:
    ID = "takctl-state"

    def inspect(self, ctx: Context) -> int:
        return TakctlStateAction().inspect(ctx)

    def apply(self, ctx: Context) -> int:
        return TakctlStateAction().apply(ctx)


ACTION = _Wrapper()
