from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tak_installer.util import log


DST_ROOT = Path("/opt/tak/tools/takctl")
DST_CONF = DST_ROOT / "takctl.conf"
DST_SECRETS = DST_ROOT / "secrets.conf"
LEGACY_DB_ENV = DST_ROOT / "secrets" / "db.env"


def _src_root(ctx) -> Path:
    return Path(ctx.repo_root) / "takctl"


def _src_conf(ctx) -> Path:
    return _src_root(ctx) / "takctl.conf.template"


def _src_secrets(ctx) -> Path:
    return _src_root(ctx) / "secrets.conf.template"


def _write_atomic(path: Path, data: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)


def _copy_text_file(src: Path, dst: Path, mode: int) -> None:
    if not src.exists():
        raise FileNotFoundError(str(src))
    _write_atomic(dst, src.read_text(encoding="utf-8"), mode)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _migrate_legacy_db_env_to_secrets() -> bool:
    if DST_SECRETS.exists():
        return False
    if not LEGACY_DB_ENV.exists():
        return False

    kv = _parse_env_file(LEGACY_DB_ENV)
    db_password = (kv.get("TAKCTL_DB_PASSWORD") or "").strip()

    content = (
        "[takctl]\n"
        f"db_password = {db_password}\n"
        "ca_signing_p12_pass = \n"
        "bedrock_api_key = \n"
    )
    _write_atomic(DST_SECRETS, content, 0o640)
    subprocess.run(["chown", "tak:tak", str(DST_SECRETS)], check=False)
    log.info("takctl-config: migrated legacy %s -> %s", LEGACY_DB_ENV, DST_SECRETS)
    return True


def apply(ctx) -> None:
    src_conf = _src_conf(ctx)
    src_secrets = _src_secrets(ctx)

    if not src_conf.exists():
        raise RuntimeError(f"missing source config template: {src_conf}")

    DST_ROOT.mkdir(parents=True, exist_ok=True)

    _copy_text_file(src_conf, DST_CONF, 0o640)
    subprocess.run(["chown", "tak:tak", str(DST_CONF)], check=False)
    log.info("takctl-config: installed %s from %s", DST_CONF, src_conf)

    if DST_SECRETS.exists():
        log.info("takctl-config: keeping existing runtime secrets: %s", DST_SECRETS)
    elif src_secrets.exists():
        _copy_text_file(src_secrets, DST_SECRETS, 0o640)
        subprocess.run(["chown", "tak:tak", str(DST_SECRETS)], check=False)
        log.info("takctl-config: installed %s from %s", DST_SECRETS, src_secrets)
    elif _migrate_legacy_db_env_to_secrets():
        pass
    else:
        log.info("takctl-config: no source secrets template and no legacy db.env; runtime secrets.conf not installed")


class _Action:
    ID = "takctl-config"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  src conf template: %s", _src_conf(ctx))
        log.info("  dst conf: %s", DST_CONF)
        log.info("  src secrets template: %s", _src_secrets(ctx))
        log.info("  dst secrets: %s", DST_SECRETS)
        log.info("  legacy db env: %s", LEGACY_DB_ENV)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
