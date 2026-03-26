from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


class UserMgrError(RuntimeError):
    pass


@dataclass(frozen=True)
class UserStatus:
    username: str
    raw: str


@dataclass(frozen=True)
class CertStatus:
    cert_path: str
    raw: str


class UserMgrService:
    """
    Thin wrapper around the path-locked sudo helper:
      /opt/tak/tools/takctl/bin/takctl-usermgr

    Helper runs as root and only allows:
      java -jar /opt/tak/utils/UserManager.jar usermod ...
      java -jar /opt/tak/utils/UserManager.jar certmod ...
    """

    def __init__(self, helper_path: str = "/opt/tak/tools/takctl/bin/takctl-usermgr"):
        self.helper = Path(helper_path)

    def preflight(self) -> None:
        if not self.helper.exists():
            raise UserMgrError(f"Missing helper: {self.helper}")
        if not self.helper.is_file():
            raise UserMgrError(f"Helper is not a file: {self.helper}")
        if not os.access(str(self.helper), os.X_OK):
            raise UserMgrError(f"Helper not executable: {self.helper}")

        # Ensure sudo non-interactive is possible (NOPASSWD expected)
        try:
            p = subprocess.run(
                ["sudo", "-n", str(self.helper), "usermod"],
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as e:
            raise UserMgrError("sudo not found") from e

        combined = ((p.stdout or "") + (p.stderr or "")).lower()

        # Only treat this as a sudo password problem when sudo itself says so.
        sudo_password_markers = [
            "sudo:",
            "a password is required",
            "password is required",
            "sorry, try again",
        ]
        if p.returncode != 0 and any(m in combined for m in sudo_password_markers):
            raise UserMgrError(
                "sudo requires a password for takctl-usermgr.\n"
                "Fix: add NOPASSWD sudoers rule for %tak on the helper."
            )

    def _run(self, subcmd: str, args: List[str]) -> Tuple[int, str]:
        if subcmd not in ("usermod", "certmod"):
            raise UserMgrError(f"Unsupported subcommand: {subcmd}")

        cmd = ["sudo", "-n", str(self.helper), subcmd] + args
        try:
            p = subprocess.run(cmd, text=True, capture_output=True)
        except FileNotFoundError as e:
            raise UserMgrError(f"Missing binary: {e.filename}") from e

        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out.strip()

    # --------------------
    # Users (usermod)
    # --------------------
    def user_status(self, username: str) -> UserStatus:
        rc, out = self._run("usermod", ["-s", username])
        if rc != 0:
            raise UserMgrError(out or f"Failed to get status for user: {username}")
        return UserStatus(username=username, raw=out)

    def user_delete(self, username: str) -> str:
        rc, out = self._run("usermod", ["-D", username])
        if rc != 0:
            raise UserMgrError(out or f"Failed to delete user: {username}")
        return out

    def user_set(
        self,
        username: str,
        *,
        password: Optional[str] = None,
        admin: Optional[bool] = None,
        fingerprint: Optional[str] = None,
        certificate_path: Optional[str] = None,
        groups: Optional[List[str]] = None,
        in_groups: Optional[List[str]] = None,
        out_groups: Optional[List[str]] = None,
        append: bool = False,
        remove: bool = False,
    ) -> str:
        """
        Map exactly to UserManager.jar usermod options.

        Flags:
          -p/--password <pw>
          -A/--administrator
          -f/--fingerprint <fp>
          -c/--certificate <certpath>
          -g/--group <group>         (repeatable)
          -ig/--in-group <group>     (repeatable)
          -og/--out-group <group>    (repeatable)
          -a/--append                (boolean)
          -r/--remove                (boolean; changes semantics of group mods)
        """
        args: List[str] = []

        if admin is True:
            args += ["-A"]
        # admin=False: do nothing (no documented "remove admin" flag)

        if password is not None:
            args += ["-p", password]

        if fingerprint is not None:
            args += ["-f", fingerprint]

        if certificate_path is not None:
            args += ["-c", certificate_path]

        # group args are repeatable: -g X -g Y ...
        if groups:
            for g in groups:
                args += ["-g", g]
        if in_groups:
            for g in in_groups:
                args += ["-ig", g]
        if out_groups:
            for g in out_groups:
                args += ["-og", g]

        if append:
            args += ["-a"]

        if remove:
            args += ["-r"]

        args += [username]

        rc, out = self._run("usermod", args)
        if rc != 0:
            raise UserMgrError(out or f"Failed to modify user: {username}")
        return out

    # --------------------
    # Certs (certmod)
    # --------------------
    def cert_status(self, cert_path: str) -> CertStatus:
        rc, out = self._run("certmod", ["-s", cert_path])
        if rc != 0:
            raise UserMgrError(out or f"Failed to get status for cert: {cert_path}")
        return CertStatus(cert_path=cert_path, raw=out)

    def cert_delete(self, cert_path: str) -> str:
        rc, out = self._run("certmod", ["-D", cert_path])
        if rc != 0:
            raise UserMgrError(out or f"Failed to delete cert mapping: {cert_path}")
        return out

    def cert_set(
        self,
        cert_path: str,
        *,
        password: Optional[str] = None,
        admin: Optional[bool] = None,
        fingerprint_override: Optional[str] = None,
        groups: Optional[List[str]] = None,
        in_groups: Optional[List[str]] = None,
        out_groups: Optional[List[str]] = None,
        append: bool = False,
        remove: bool = False,
    ) -> str:
        """
        Map exactly to UserManager.jar certmod options.

        Flags:
          -A/--administrator
          -p/--password <pw>
          -f/--fingerprint <fp>    (override certificate fingerprint)
          -g/-ig/-og repeatable
          -a append (boolean)
          -r remove (boolean; changes semantics of group mods)
        """
        args: List[str] = []

        if admin is True:
            args += ["-A"]

        if password is not None:
            args += ["-p", password]

        if fingerprint_override is not None:
            args += ["-f", fingerprint_override]

        if groups:
            for g in groups:
                args += ["-g", g]
        if in_groups:
            for g in in_groups:
                args += ["-ig", g]
        if out_groups:
            for g in out_groups:
                args += ["-og", g]

        if append:
            args += ["-a"]

        if remove:
            args += ["-r"]

        args += [cert_path]

        rc, out = self._run("certmod", args)
        if rc != 0:
            raise UserMgrError(out or f"Failed to modify cert mapping: {cert_path}")
        return out

