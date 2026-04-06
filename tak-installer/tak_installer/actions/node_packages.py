from __future__ import annotations

import subprocess
from pathlib import Path

from tak_installer.log import get_logger

log = get_logger(__name__)

PACKAGES = [
    "poppler-utils",
    "python3-venv",
    "python3.10-venv",
    "python3-pip",
    "rsync",
    "nginx",
    "certbot",
]


REPLAY_PACKAGES = [
]

def _parse_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out

def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}

def _replay_enabled(ctx) -> bool:
    runtime_conf = Path("/opt/tak/tools/takctl/conf.d/replay.conf")
    merged = _parse_simple_kv(runtime_conf)
    return _truthy(merged.get("replay_enabled", "false"))

def _packages_for_ctx(ctx) -> list[str]:
    pkgs = list(PACKAGES)
    if _replay_enabled(ctx):
        pkgs.extend(REPLAY_PACKAGES)
    return pkgs

def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}:\n{' '.join(cmd)}\n\n{p.stdout}")
    if (p.stdout or "").strip():
        log.info((p.stdout or "").strip())

class _Action:
    ID = "node-packages"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  replay_enabled: %s", str(_replay_enabled(ctx)).lower())
        log.info("  packages: %s", ", ".join(_packages_for_ctx(ctx)))
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        _run(["apt-get", "update"])
        packages = _packages_for_ctx(ctx)
        _run(["apt-get", "install", "-y", *packages])
        log.info("%s: ready", self.ID)
        return 0

ACTION = _Action()
