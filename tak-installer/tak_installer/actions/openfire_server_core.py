from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tak_installer.engine import Context

PACKAGE = "openfire"
SERVICE = "openfire"
DEFAULT_VERSION = "5.0.4"
CACHE_DIR = Path("/opt/tak/cache/openfire")


def _env_first(env: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        v = str(env.get(key, "") or "").strip()
        if v:
            return v
    return default


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _cfg(ctx: Context) -> dict[str, str]:
    env = dict(ctx.env or {})
    version = _env_first(
        env,
        "openfire_version",
        "OPENFIRE_VERSION",
        default=DEFAULT_VERSION,
    )
    enabled = _truthy(
        _env_first(
            env,
            "openfire_enabled",
            "OPENFIRE_ENABLED",
            default="false",
        )
    )
    return {
        "enabled": "true" if enabled else "false",
        "version": version,
        "deb_url": f"https://download.igniterealtime.org/openfire/openfire_{version}_all.deb",
    }


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out = (p.stdout or "").strip()
    if out:
        print(out)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"command failed rc={p.returncode}: {' '.join(cmd)}\n\n{p.stdout}"
        )
    return p


def _pkg_version() -> str:
    p = subprocess.run(
        ["dpkg-query", "-W", "-f", "${Version}", PACKAGE],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if p.returncode != 0:
        return ""
    return str(p.stdout or "").strip()


def _systemctl_state(cmd: str) -> str:
    p = subprocess.run(
        ["systemctl", cmd, SERVICE],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return str(p.stdout or "").strip()


@dataclass(frozen=True)
class _Action:
    ID: str = "openfire_server.core"

    def inspect(self, ctx: Context) -> int:
        cfg = _cfg(ctx)
        installed = _pkg_version()
        enabled = _systemctl_state("is-enabled")
        active = _systemctl_state("is-active")

        print("openfire_server.core")
        print(f"  openfire_enabled: {cfg['enabled']}")
        print(f"  desired_version:  {cfg['version']}")
        print(f"  installed_version:{installed or '(not installed)'}")
        print(f"  service_enabled:  {enabled or '(unknown)'}")
        print(f"  service_active:   {active or '(unknown)'}")
        print(f"  deb_url:          {cfg['deb_url']}")
        return 0

    def apply(self, ctx: Context) -> int:
        cfg = _cfg(ctx)
        if cfg["enabled"] != "true":
            print("applied: openfire_server.core skipped (openfire_enabled != true)")
            return 0

        version = cfg["version"]
        deb_url = cfg["deb_url"]
        deb_name = f"openfire_{version}_all.deb"
        deb_path = CACHE_DIR / deb_name

        _run(["sudo", "apt-get", "update"])
        _run([
            "sudo", "apt-get", "install", "-y",
            "ca-certificates",
            "curl",
        ])

        java_ok = subprocess.run(
            ["bash", "-lc", "command -v java >/dev/null 2>&1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0

        if java_ok:
            print("openfire_server.core: java already present")
        else:
            print("openfire_server.core: java missing, installing default-jre-headless")
            _run(["sudo", "apt-get", "install", "-y", "default-jre-headless"])

        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        installed = _pkg_version()
        if installed != version:
            print(f"openfire_server.core: downloading {deb_url}")
            _run(["sudo", "curl", "-fL", "-o", str(deb_path), deb_url])

            p = _run(["sudo", "dpkg", "-i", str(deb_path)], check=False)
            if p.returncode != 0:
                _run(["sudo", "apt-get", "install", "-f", "-y"])
        else:
            print(f"openfire_server.core: package already at desired version {version}")

        _run(["sudo", "systemctl", "daemon-reload"], check=False)
        _run(["sudo", "systemctl", "enable", SERVICE])
        _run(["sudo", "systemctl", "restart", SERVICE])

        final_version = _pkg_version()
        final_active = _systemctl_state("is-active")
        print(
            f"applied: openfire_server.core "
            f"(version={final_version or 'unknown'} active={final_active or 'unknown'})"
        )
        return 0


ACTION = _Action()
