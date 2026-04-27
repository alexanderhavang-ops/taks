from __future__ import annotations

import grp
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context
from tak_installer.runtime_state import get_fqdn
from takctl.onboarding.policy import Policy
from takctl.onboarding.voice_topology import derive_voice_topology


PACKAGE = "mumble-server"
SERVICE = "mumble-server"
CONFIG = Path("/etc/mumble/mumble-server.ini")
TLS_DIR = Path("/etc/mumble-server/tls")
HOOK = Path("/etc/letsencrypt/renewal-hooks/deploy/90-mumble-server-cert-refresh")

SECRET_DIR = Path("/opt/tak/tools/takctl/secrets.d")
SECRET_FILE = SECRET_DIR / "murmur.conf"

LEGACY_SECRET_DIR = Path("/opt/tak/bootstrap/secrets.d")
LEGACY_SECRET_FILE = LEGACY_SECRET_DIR / "murmur.conf"

SECRET_KEY = "serverpassword"
DB = Path("/var/lib/mumble-server/mumble-server.sqlite")
DEFAULT_CHANNELS: list[str] = []


def _node_unit_id(ctx: Context) -> str:
    fqdn = str(get_fqdn(ctx) or "").strip().lower()
    if not fqdn:
        raise RuntimeError("mumble_server.core: missing fqdn")
    return fqdn.split(".", 1)[0].strip()


def _desired_channels(ctx: Context) -> list[str]:
    unit = _node_unit_id(ctx)
    policy = Policy()
    topo = derive_voice_topology(policy.cfg, {"unit": unit, "policy_id": policy.policy_id})
    channels = [str(x).strip() for x in (topo.get("channels") or []) if str(x or "").strip()]
    if not channels:
        raise RuntimeError(f"mumble_server.core: voice topology produced no channels for unit={unit}")
    return channels


def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


def _capture(cmd: list[str]) -> str:
    cp = _run(cmd, check=False, capture=True)
    return (cp.stdout or cp.stderr or "").strip()


def _sudo_install_text(
    dst: Path,
    content: str,
    mode: str = "0644",
    owner: str = "root",
    group: str = "root",
) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".tmp") as tf:
        tf.write(content)
        tmp = tf.name
    try:
        _run(["sudo", "install", "-o", owner, "-g", group, "-m", mode, tmp, str(dst)], check=True)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _pkg_status() -> tuple[bool, str]:
    out = _capture(["sudo", "dpkg-query", "-W", "-f=${Status} ${Version}\n", PACKAGE])
    prefix = "install ok installed "
    if out.startswith(prefix):
        return True, out[len(prefix):].strip()
    return False, ""


def _systemctl_state(verb: str) -> str:
    return _capture(["sudo", "systemctl", verb, SERVICE])


def _lineages() -> list[Path]:
    base = Path("/etc/letsencrypt/live")
    out: list[Path] = []
    if not base.is_dir():
        return out
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if (p / "fullchain.pem").exists() and (p / "privkey.pem").exists():
            out.append(p)
    return out


def _configured_lineage() -> Path | None:
    if not HOOK.exists():
        return None
    try:
        s = HOOK.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r'^LINEAGE="([^"]+)"$', s, flags=re.MULTILINE)
    if not m:
        return None
    p = Path(m.group(1))
    if (p / "fullchain.pem").exists() and (p / "privkey.pem").exists():
        return p
    return None


def _choose_lineage() -> Path:
    existing = _configured_lineage()
    if existing is not None:
        return existing

    found = _lineages()
    if len(found) == 1:
        return found[0]
    if not found:
        raise RuntimeError("no letsencrypt lineage with fullchain.pem + privkey.pem found under /etc/letsencrypt/live")
    raise RuntimeError(
        "multiple letsencrypt lineages found; refusing to guess: " + ", ".join(str(p) for p in found)
    )


def _set_kv_value(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pat = re.compile(rf"^[;#]?\s*{re.escape(key)}\s*=.*$", flags=re.MULTILINE)
    if pat.search(text):
        return pat.sub(line, text, count=1)
    if not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def _get_kv_value(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s*=(.*)$", text, flags=re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip()


def _secret_group() -> str:
    try:
        grp.getgrnam("tak")
        return "tak"
    except KeyError:
        return "root"


def _generate_password(length: int = 20) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_secret_text() -> str:
    current = _read_text_if_exists(SECRET_FILE)
    if current:
        return current
    legacy = _read_text_if_exists(LEGACY_SECRET_FILE)
    if legacy:
        return legacy
    return ""


def _ensure_secret_file() -> str:
    current = _read_secret_text()
    pw = _get_kv_value(current, SECRET_KEY)

    if not current:
        current = (
            "# canonical secrets for murmur/mumble-server\n"
            "# managed by tak-installer action mumble_server.core\n"
        )

    if not pw:
        pw = _generate_password()
        current = _set_kv_value(current, SECRET_KEY, pw)

    secret_group = _secret_group()
    _run(
        [
            "sudo",
            "install",
            "-d",
            "-o",
            "root",
            "-g",
            secret_group,
            "-m",
            "0750",
            str(SECRET_DIR),
        ],
        check=True,
    )
    _sudo_install_text(
        SECRET_FILE,
        current,
        mode="0640",
        owner="root",
        group=secret_group,
    )
    return pw


def _managed_config_text(lineage: Path, server_password: str) -> str:
    if not CONFIG.exists():
        raise RuntimeError(f"missing config file: {CONFIG}")

    s = CONFIG.read_text(encoding="utf-8")
    s = _set_kv_value(s, "serverpassword", server_password)
    s = _set_kv_value(s, "sslCert", str(TLS_DIR / "fullchain.pem"))
    s = _set_kv_value(s, "sslKey", str(TLS_DIR / "privkey.pem"))
    if (lineage / "chain.pem").exists():
        s = _set_kv_value(s, "sslCA", str(TLS_DIR / "chain.pem"))
    else:
        s = _set_kv_value(s, "sslCA", "")
    s = _set_kv_value(s, "certrequired", "false")
    return s


def _install_tls_material(lineage: Path) -> None:
    _run(
        [
            "sudo",
            "install",
            "-d",
            "-o",
            "root",
            "-g",
            "mumble-server",
            "-m",
            "0750",
            str(TLS_DIR),
        ],
        check=True,
    )
    _run(
        [
            "sudo",
            "install",
            "-o",
            "root",
            "-g",
            "root",
            "-m",
            "0644",
            str(lineage / "fullchain.pem"),
            str(TLS_DIR / "fullchain.pem"),
        ],
        check=True,
    )
    _run(
        [
            "sudo",
            "install",
            "-o",
            "root",
            "-g",
            "mumble-server",
            "-m",
            "0640",
            str(lineage / "privkey.pem"),
            str(TLS_DIR / "privkey.pem"),
        ],
        check=True,
    )
    if (lineage / "chain.pem").exists():
        _run(
            [
                "sudo",
                "install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0644",
                str(lineage / "chain.pem"),
                str(TLS_DIR / "chain.pem"),
            ],
            check=True,
        )
    else:
        _run(["sudo", "rm", "-f", str(TLS_DIR / "chain.pem")], check=True)


def _hook_text(lineage: Path) -> str:
    return f"""#!/bin/sh
set -eu
LINEAGE="{lineage}"
DST="{TLS_DIR}"

install -d -o root -g mumble-server -m 0750 "$DST"
install -o root -g root -m 0644 "$LINEAGE/fullchain.pem" "$DST/fullchain.pem"
install -o root -g mumble-server -m 0640 "$LINEAGE/privkey.pem" "$DST/privkey.pem"

if [ -f "$LINEAGE/chain.pem" ]; then
  install -o root -g root -m 0644 "$LINEAGE/chain.pem" "$DST/chain.pem"
else
  rm -f "$DST/chain.pem"
fi

systemctl restart mumble-server
"""


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    bp = path.with_name(path.name + ".bak.taks")
    _run(["sudo", "cp", "-a", str(path), str(bp)], check=True)
    return bp


def _restore(src: Path | None, dst: Path) -> None:
    if src is None:
        return
    _run(["sudo", "cp", "-a", str(src), str(dst)], check=True)


def _seed_default_channels_if_empty(ctx: Context) -> bool:
    if not DB.exists():
        return False

    desired = _desired_channels(ctx)

    con = sqlite3.connect(str(DB))
    try:
        cur = con.cursor()
        rows = cur.execute(
            "select server_id, channel_id, parent_id, name, inheritacl from channels order by channel_id"
        ).fetchall()

        if len(rows) != 1:
            return False

        server_id, channel_id, parent_id, name, inheritacl = rows[0]
        if channel_id != 0 or name != "Root":
            return False

        next_id = 1
        for ch_name in desired:
            cur.execute(
                "insert into channels (server_id, channel_id, parent_id, name, inheritacl) values (?, ?, ?, ?, ?)",
                (server_id, next_id, 0, ch_name, 1),
            )
            next_id += 1

        con.commit()
        return True
    finally:
        con.close()



def _ensure_db_read_access() -> None:
    db_dir = DB.parent

    if db_dir.exists():
        _run(["sudo", "chgrp", "tak", str(db_dir)], check=False)
        _run(["sudo", "chmod", "2750", str(db_dir)], check=False)

        for cur in sorted(db_dir.glob("mumble-server.sqlite*")):
            if not cur.exists():
                continue
            _run(["sudo", "chgrp", "tak", str(cur)], check=False)
            _run(["sudo", "chmod", "0640", str(cur)], check=False)


@dataclass(frozen=True)
class _Action:
    ID: str = "mumble_server.core"

    def inspect(self, ctx: Context) -> int:
        installed, version = _pkg_status()
        enabled = _systemctl_state("is-enabled")
        active = _systemctl_state("is-active")
        cfg = str(CONFIG) if CONFIG.exists() else ""
        lineages = _lineages()
        chosen = ""
        try:
            chosen = str(_choose_lineage())
        except Exception as e:
            chosen = f"ERROR: {e}"

        secret_present = SECRET_FILE.exists()
        legacy_secret_present = LEGACY_SECRET_FILE.exists()
        secret_text = _read_secret_text()
        password = _get_kv_value(secret_text, SECRET_KEY)
        password_len = len(password) if password else 0

        print("Mumble server core (package + tls + canonical secret + systemd)")
        print(f"  package: {PACKAGE}")
        print(f"  installed: {str(installed).lower()}")
        print(f"  version: {version}")
        print(f"  service enabled: {enabled}")
        print(f"  service active: {active}")
        print(f"  config path: {cfg}")
        print(f"  tls dir: {TLS_DIR}")
        print(f"  canonical secret file: {SECRET_FILE}")
        print(f"  canonical secret present: {str(secret_present).lower()}")
        print(f"  legacy secret file: {LEGACY_SECRET_FILE}")
        print(f"  legacy secret present: {str(legacy_secret_present).lower()}")
        print(f"  canonical {SECRET_KEY} length: {password_len}")
        print(f"  hook path: {HOOK}")
        print(f"  db path: {DB}")
        print(f"  default channels: {', '.join(DEFAULT_CHANNELS)}")
        print("  lineages found:")
        if lineages:
            for p in lineages:
                print(f"    {p}")
        else:
            print("    (none)")
        print(f"  chosen lineage: {chosen}")
        print("  listeners:")
        ss = _capture(["sudo", "ss", "-luntp"])
        lines = [line for line in ss.splitlines() if "64738" in line]
        if lines:
            for line in lines:
                print(f"    {line}")
        else:
            print("    (no :64738 listener found)")
        print("  dry-run: no changes performed.")
        return 0

    def apply(self, ctx: Context) -> int:
        config_backup: Path | None = None
        hook_backup: Path | None = None
        secret_backup: Path | None = None
        db_backup: Path | None = None

        try:
            _run(["sudo", "apt-get", "update"], check=True)
            _run(
                [
                    "sudo",
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    "apt-get",
                    "install",
                    "-y",
                    PACKAGE,
                ],
                check=True,
            )

            if not CONFIG.exists():
                raise RuntimeError(f"expected config file after install: {CONFIG}")

            lineage = _choose_lineage()

            config_backup = _backup(CONFIG)
            hook_backup = _backup(HOOK)
            secret_backup = _backup(SECRET_FILE)

            server_password = _ensure_secret_file()
            _install_tls_material(lineage)

            cfg_text = _managed_config_text(lineage, server_password)
            _sudo_install_text(
                CONFIG,
                cfg_text,
                mode="0640",
                owner="root",
                group="mumble-server",
            )

            _run(["sudo", "mkdir", "-p", str(HOOK.parent)], check=True)
            _sudo_install_text(HOOK, _hook_text(lineage), mode="0755")

            _run(["sudo", "systemctl", "stop", SERVICE], check=False)
            db_backup = _backup(DB)
            seeded = _seed_default_channels_if_empty(ctx)
            _ensure_db_read_access()

            _run(["sudo", "systemctl", "enable", "--now", SERVICE], check=True)
            _run(["sudo", "systemctl", "restart", SERVICE], check=True)

            active = _systemctl_state("is-active")
            if active != "active":
                raise RuntimeError(f"{SERVICE} is not active after apply: {active}")

            version = _pkg_status()[1]
            print(
                f"applied: mumble_server.core "
                f"(changed=true, version={version}, lineage={lineage}, secret_file={SECRET_FILE}, seeded_channels={str(seeded).lower()})"
            )
            return 0

        except Exception as e:
            print(f"ERROR: mumble_server.core failed: {e}")
            print("ERROR: attempting rollback of config + hook + canonical secret...")
            try:
                _restore(config_backup, CONFIG)
            except Exception as re:
                print(f"ERROR: rollback config failed: {re}")
            try:
                _restore(hook_backup, HOOK)
            except Exception as re:
                print(f"ERROR: rollback hook failed: {re}")
            try:
                _restore(secret_backup, SECRET_FILE)
            except Exception as re:
                print(f"ERROR: rollback secret failed: {re}")
            try:
                _restore(db_backup, DB)
            except Exception as re:
                print(f"ERROR: rollback db failed: {re}")
            try:
                _run(["sudo", "systemctl", "restart", SERVICE], check=False)
            except Exception:
                pass
            return 2


ACTION = _Action()
