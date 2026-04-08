from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.log import get_logger

log = get_logger(__name__)

STATE_ROOT = Path("/opt/tak/takctl-state")

# Installer-owned state files (safe to overwrite each apply)
APPLY_JSON = STATE_ROOT / "apply.json"


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


@dataclass
class TakctlStateAction:
    """
    Ensures installer-owned runtime state directories exist.
    """

    def inspect(self, ctx: Context) -> int:
        return 0

    def apply(self, ctx: Context) -> int:
        log.info("takctl-state: ensuring runtime state directories exist")

        # Base state root
        STATE_ROOT.mkdir(parents=True, exist_ok=True)

        # Onboarding runtime
        (STATE_ROOT / "onboarding" / "users").mkdir(parents=True, exist_ok=True)
        (STATE_ROOT / "onboarding" / "identities").mkdir(parents=True, exist_ok=True)

        # Runtime policy overrides (orchestrator-controlled)
        (STATE_ROOT / "policies.d").mkdir(parents=True, exist_ok=True)

        _fix_state_perms()

        # Apply token written every apply
        _write_apply_token(ctx)
        _fix_state_perms()

        log.info("takctl-state: ready")
        return 0


class _Wrapper:
    ID = "takctl-state"

    def inspect(self, ctx: Context) -> int:
        return TakctlStateAction().inspect(ctx)

    def apply(self, ctx: Context) -> int:
        return TakctlStateAction().apply(ctx)


ACTION = _Wrapper()
