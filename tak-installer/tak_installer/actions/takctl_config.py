from __future__ import annotations

import secrets
import shutil
import subprocess
from pathlib import Path

from tak_installer.util import log
from tak_installer.config_seed import (
    BOOTSTRAP_CONFIG_DIRS,
    BOOTSTRAP_SECRETS_DIRS,
    materialize_component_dir_once,
)


DST_ROOT = Path("/opt/tak/tools/takctl")
DST_CONF_D = DST_ROOT / "conf.d"
DST_SECRETS_D = DST_ROOT / "secrets.d"
DST_CONFMETA = DST_ROOT / "confmeta"


def _src_root(ctx) -> Path:
    return Path(ctx.repo_root) / "takctl"


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
    tmp.chmod(mode)
    tmp.replace(path)


def _parse_kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _write_simple_kv(path: Path, data: dict[str, str], mode: int) -> None:
    rows = [f"{k} = {data[k]}" for k in sorted(data.keys())]
    _write_atomic(path, "\n".join(rows) + "\n", mode)


def _chown_tree(path: Path, *, file_mode: int = 0o640, dir_mode: int = 0o2770) -> None:
    if not path.exists():
        return
    subprocess.run(["chown", "-R", "tak:tak", str(path)], check=False)
    subprocess.run(
        ["bash", "-lc", f'find "{path}" -type d -exec chmod {dir_mode:o} {{}} \\; 2>/dev/null || true'],
        check=False,
    )
    subprocess.run(
        ["bash", "-lc", f'find "{path}" -type f -exec chmod {file_mode:o} {{}} \\; 2>/dev/null || true'],
        check=False,
    )


def _load_conf_dir(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for f in sorted(path.glob("*.conf")):
        out.update(_parse_kv_file(f))
    return out


def _ensure_policy_derived_runtime() -> None:
    conf = _load_conf_dir(DST_CONF_D)
    policy_id = str(conf.get("default_policy_id") or "").strip().lower()
    if not policy_id:
        raise RuntimeError("takctl-config: default_policy_id missing after conf.d materialization")

    replay_enabled = "true" if policy_id == "hemvarnet" else "false"

    replay_path = DST_CONF_D / "replay.conf"
    replay = _parse_kv_file(replay_path)
    replay["replay_enabled"] = replay_enabled
    _write_simple_kv(replay_path, replay, 0o640)

    log.info(
        "takctl-config: derived replay.conf from default_policy_id=%s (replay_enabled=%s)",
        policy_id,
        replay_enabled,
    )


def _ensure_generated_secrets() -> None:
    certs_path = DST_SECRETS_D / "certs.conf"
    certs = _parse_kv_file(certs_path)

    changed = False
    if not (certs.get("cert_capass") or "").strip():
        certs["cert_capass"] = secrets.token_urlsafe(24)
        changed = True
    if not (certs.get("cert_pass") or "").strip():
        certs["cert_pass"] = certs["cert_capass"]
        changed = True

    if changed or not certs_path.exists():
        _write_simple_kv(certs_path, certs, 0o640)
        log.info("takctl-config: ensured installer-owned cert secrets in %s", certs_path)


def apply(ctx) -> None:
    src_conf_d = _src_conf_d(ctx)
    src_secrets_d = _src_secrets_d(ctx)
    src_confmeta = _src_confmeta(ctx)

    if not src_conf_d.is_dir():
        raise RuntimeError(f"missing source conf.d: {src_conf_d}")
    if not src_secrets_d.is_dir():
        raise RuntimeError(f"missing source secrets.d: {src_secrets_d}")

    DST_ROOT.mkdir(parents=True, exist_ok=True)

    n_conf = materialize_component_dir_once(
        src_dir=src_conf_d,
        bootstrap_dirs=BOOTSTRAP_CONFIG_DIRS,
        dst_dir=DST_CONF_D,
        mode=0o640,
    )
    log.info("takctl-config: materialized %s conf.d files into %s", n_conf, DST_CONF_D)

    n_sec = materialize_component_dir_once(
        src_dir=src_secrets_d,
        bootstrap_dirs=BOOTSTRAP_SECRETS_DIRS,
        dst_dir=DST_SECRETS_D,
        mode=0o640,
    )
    log.info("takctl-config: materialized %s secrets.d files into %s", n_sec, DST_SECRETS_D)

    _ensure_generated_secrets()
    _ensure_policy_derived_runtime()

    _chown_tree(DST_CONF_D, file_mode=0o640, dir_mode=0o2770)
    _chown_tree(DST_SECRETS_D, file_mode=0o640, dir_mode=0o2770)

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

    _chown_tree(DST_CONFMETA, file_mode=0o644, dir_mode=0o2755)
    log.info("takctl-config: installed %s confmeta files into %s", n_meta, DST_CONFMETA)


class _Action:
    ID = "takctl-config"

    def inspect(self, ctx) -> int:
        log.info("Inspecting %s action...", self.ID)
        log.info("  src conf.d: %s", _src_conf_d(ctx))
        log.info("  dst conf.d: %s", DST_CONF_D)
        log.info("  bootstrap conf.d: %s", BOOTSTRAP_CONFIG_DIRS)
        log.info("  src secrets.d: %s", _src_secrets_d(ctx))
        log.info("  dst secrets.d: %s", DST_SECRETS_D)
        log.info("  bootstrap secrets.d: %s", BOOTSTRAP_SECRETS_DIRS)
        log.info("  src confmeta: %s", _src_confmeta(ctx))
        log.info("  dst confmeta: %s", DST_CONFMETA)
        return 0

    def apply(self, ctx) -> int:
        log.info("Applying %s action...", self.ID)
        apply(ctx)
        return 0


ACTION = _Action()
