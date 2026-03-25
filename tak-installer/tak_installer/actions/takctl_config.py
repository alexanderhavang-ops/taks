from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log


DST_ROOT = Path("/opt/tak/tools/takctl")
DST_CONF = DST_ROOT / "takctl.conf"
DST_SECRETS = DST_ROOT / "secrets.conf"
DST_CONF_D = DST_ROOT / "conf.d"
DST_SECRETS_D = DST_ROOT / "secrets.d"
DST_CONFMETA = DST_ROOT / "confmeta"
LEGACY_DB_ENV = DST_ROOT / "secrets" / "db.env"


def _src_root(ctx) -> Path:
    return Path(ctx.repo_root) / "takctl"


def _src_conf(ctx) -> Path:
    return _src_root(ctx) / "takctl.conf.template"


def _src_secrets(ctx) -> Path:
    return _src_root(ctx) / "secrets.conf.template"


def _src_conf_d(ctx) -> Path:
    return _src_root(ctx) / "conf.d"


def _src_secrets_d(ctx) -> Path:
    return _src_root(ctx) / "secrets.d"


def _src_confmeta(ctx) -> Path:
    return _src_root(ctx) / "confmeta"


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


def _copy_tree_text(src_dir: Path, dst_dir: Path, *, mode: int) -> int:
    if not src_dir.exists() or not src_dir.is_dir():
        return 0

    dst_dir.mkdir(parents=True, exist_ok=True)

    for old in dst_dir.iterdir():
        if old.is_file() or old.is_symlink():
            old.unlink()
        elif old.is_dir():
            shutil.rmtree(old)

    n = 0
    for src in sorted(src_dir.iterdir()):
        if not src.is_file():
            continue
        dst = dst_dir / src.name
        _write_atomic(dst, src.read_text(encoding="utf-8"), mode)
        n += 1
    return n


def _migrate_legacy_db_env_to_secrets() -> bool:
    if DST_SECRETS.exists():
        return False
    if not LEGACY_DB_ENV.exists():
        return False

    kv = _parse_env_file(LEGACY_DB_ENV)
    db_password = (kv.get("TAKCTL_DB_PASSWORD") or "").strip()

    content = (
        "[takctl-secrets]\n"
        f"db_password = {db_password}\n"
        "ca_signing_p12_pass = \n"
        "user_key_pass = \n"
        "onboarding_client_p12_default_pass = \n"
        "marti_api_username = \n"
        "marti_api_password = \n"
        "bedrock_api_key = \n"
    )
    _write_atomic(DST_SECRETS, content, 0o640)
    subprocess.run(["chown", "tak:tak", str(DST_SECRETS)], check=False)
    log.info("takctl-config: migrated legacy %s -> %s", LEGACY_DB_ENV, DST_SECRETS)
    return True


def apply(ctx) -> None:
    src_conf = _src_conf(ctx)
    src_secrets = _src_secrets(ctx)
    src_conf_d = _src_conf_d(ctx)
    src_secrets_d = _src_secrets_d(ctx)
    src_confmeta = _src_confmeta(ctx)

    if not src_conf.exists():
        raise RuntimeError(f"missing source config template: {src_conf}")

    DST_ROOT.mkdir(parents=True, exist_ok=True)

    # Keep legacy files for compatibility/fallback during migration.
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

    n_conf = _copy_tree_text(src_conf_d, DST_CONF_D, mode=0o640)
    subprocess.run(["chown", "-R", "tak:tak", str(DST_CONF_D)], check=False)
    log.info("takctl-config: installed %s conf.d files into %s", n_conf, DST_CONF_D)

    n_sec = _copy_tree_text(src_secrets_d, DST_SECRETS_D, mode=0o640)
    subprocess.run(["chown", "-R", "tak:tak", str(DST_SECRETS_D)], check=False)
    log.info("takctl-config: installed %s secrets.d files into %s", n_sec, DST_SECRETS_D)

    n_meta = _copy_tree_text(src_confmeta, DST_CONFMETA, mode=0o644)
    subprocess.run(["chown", "-R", "tak:tak", str(DST_CONFMETA)], check=False)
    log.info("takctl-config: installed %s confmeta files into %s", n_meta, DST_CONFMETA)


class _Action:
    ID = "takctl-config"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  src conf template: %s", _src_conf(ctx))
        log.info("  dst conf: %s", DST_CONF)
        log.info("  src secrets template: %s", _src_secrets(ctx))
        log.info("  dst secrets: %s", DST_SECRETS)
        log.info("  src conf.d: %s", _src_conf_d(ctx))
        log.info("  dst conf.d: %s", DST_CONF_D)
        log.info("  src secrets.d: %s", _src_secrets_d(ctx))
        log.info("  dst secrets.d: %s", DST_SECRETS_D)
        log.info("  src confmeta: %s", _src_confmeta(ctx))
        log.info("  dst confmeta: %s", DST_CONFMETA)
        log.info("  legacy db env: %s", LEGACY_DB_ENV)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
