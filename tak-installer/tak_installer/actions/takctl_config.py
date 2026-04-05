from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log
from tak_installer.config_seed import (
    BOOTSTRAP_CONFIG_DIRS,
    BOOTSTRAP_SECRETS_DIRS,
    materialize_component_dir_once,
    parse_simple_kv,
    write_simple_kv,
)


DST_ROOT = Path("/opt/tak/tools/takctl")
DST_CONF = DST_ROOT / "takctl.conf"
DST_SECRETS = DST_ROOT / "secrets.conf"
DST_CONF_D = DST_ROOT / "conf.d"
DST_SECRETS_D = DST_ROOT / "secrets.d"
DST_CONFMETA = DST_ROOT / "confmeta"
LEGACY_DB_ENV = DST_ROOT / "secrets" / "db.env"
LEGACY_DB_SPLIT_ENV = DST_ROOT / "secrets" / "db.env"
DST_DB_SECRET_SPLIT = DST_SECRETS_D / "db.conf"

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


def _migrate_legacy_db_env_to_split_secret() -> bool:
    if DST_DB_SECRET_SPLIT.exists():
        return False
    if not LEGACY_DB_SPLIT_ENV.exists():
        return False

    kv = _parse_env_file(LEGACY_DB_SPLIT_ENV)
    db_password = (kv.get("TAKCTL_DB_PASSWORD") or "").strip()

    content = f"db_password = {db_password}\n"
    _write_atomic(DST_DB_SECRET_SPLIT, content, 0o640)
    subprocess.run(["chown", "tak:tak", str(DST_DB_SECRET_SPLIT)], check=False)
    log.info("takctl-config: migrated legacy %s -> %s", LEGACY_DB_SPLIT_ENV, DST_DB_SECRET_SPLIT)
    return True



def _fix_dir_tree_owner_mode(path: Path, *, file_mode: int = 0o640, dir_mode: int = 0o2770) -> None:
    if not path.exists():
        return
    subprocess.run(["chown", "-R", "tak:tak", str(path)], check=False)
    subprocess.run(["bash", "-lc", f'find "{path}" -type d -exec chmod {dir_mode:o} {{}} \\; 2>/dev/null || true'], check=False)
    subprocess.run(["bash", "-lc", f'find "{path}" -type f -exec chmod {file_mode:o} {{}} \\; 2>/dev/null || true'], check=False)


def _ensure_generated_secrets() -> None:
    certs_path = DST_SECRETS_D / "certs.conf"
    certs = parse_simple_kv(certs_path)

    changed = False
    if not (certs.get("cert_capass") or "").strip():
        certs["cert_capass"] = secrets.token_urlsafe(24)
        changed = True
    if not (certs.get("cert_pass") or "").strip():
        certs["cert_pass"] = certs["cert_capass"]
        changed = True

    if changed or not certs_path.exists():
        write_simple_kv(certs_path, certs, 0o640)
        log.info("takctl-config: ensured installer-owned cert secrets in %s", certs_path)


def apply(ctx) -> None:
    src_conf = _src_conf(ctx)
    src_secrets = _src_secrets(ctx)
    src_conf_d = _src_conf_d(ctx)
    src_secrets_d = _src_secrets_d(ctx)
    src_confmeta = _src_confmeta(ctx)

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

    n_conf = materialize_component_dir_once(
        src_dir=src_conf_d,
        bootstrap_dirs=BOOTSTRAP_CONFIG_DIRS,
        dst_dir=DST_CONF_D,
        mode=0o640,
    )
    log.info("takctl-config: materialized %s conf.d files into %s", n_conf, DST_CONF_D)

    _migrate_legacy_db_env_to_split_secret()

    n_sec = materialize_component_dir_once(
        src_dir=src_secrets_d,
        bootstrap_dirs=BOOTSTRAP_SECRETS_DIRS,
        dst_dir=DST_SECRETS_D,
        mode=0o640,
    )
    log.info("takctl-config: materialized %s secrets.d files into %s", n_sec, DST_SECRETS_D)

    _ensure_generated_secrets()

    _fix_dir_tree_owner_mode(DST_CONF_D, file_mode=0o640, dir_mode=0o2770)
    _fix_dir_tree_owner_mode(DST_SECRETS_D, file_mode=0o640, dir_mode=0o2770)

    n_meta = 0
    if src_confmeta.exists() and src_confmeta.is_dir():
        DST_CONFMETA.mkdir(parents=True, exist_ok=True)

        for old in DST_CONFMETA.iterdir():
            if old.is_file() or old.is_symlink():
                old.unlink()
            elif old.is_dir():
                shutil.rmtree(old)

        for src in sorted(src_confmeta.iterdir()):
            if not src.is_file():
                continue
            name = src.name
            if not (name.endswith(".json.template") or name.endswith(".json")):
                continue
            dst_name = name[:-len(".template")] if name.endswith(".json.template") else name
            _write_atomic(DST_CONFMETA / dst_name, src.read_text(encoding="utf-8"), 0o644)
            n_meta += 1

    _fix_dir_tree_owner_mode(DST_CONFMETA, file_mode=0o644, dir_mode=0o2755)
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
        log.info("  bootstrap conf.d: %s", BOOTSTRAP_CONFIG_DIRS)
        log.info("  src secrets.d: %s", _src_secrets_d(ctx))
        log.info("  dst secrets.d: %s", DST_SECRETS_D)
        log.info("  bootstrap secrets.d: %s", BOOTSTRAP_SECRETS_DIRS)
        log.info("  src confmeta: %s", _src_confmeta(ctx))
        log.info("  dst confmeta: %s", DST_CONFMETA)
        log.info("  legacy db env: %s", LEGACY_DB_ENV)
        log.info("  legacy db split env: %s", LEGACY_DB_SPLIT_ENV)
        log.info("  runtime db split secret: %s", DST_DB_SECRET_SPLIT)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
