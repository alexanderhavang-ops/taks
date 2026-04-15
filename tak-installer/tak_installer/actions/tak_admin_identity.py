from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path
import xml.etree.ElementTree as ET

from takctl.config import load_config, load_secrets
from takctl.config_store import save_runtime_config_view, save_runtime_secrets_view
from takctl.services.usermgr import UserMgrService

log = logging.getLogger(__name__)

SRC_ID = "tak-admin-identity"

RUNTIME_ID_DIR = Path("/opt/tak/tools/takctl/state/admin_identity")
CERTS_ROOT = Path("/opt/tak/certs")
CERTS_DIR = Path("/opt/tak/certs/files")
MAKECERT = Path("/opt/tak/certs/makeCert.sh")
TRUSTSTORE_SRC = Path("/opt/tak/certs/files/01_TRUST/truststore-root.p12")
USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
XML_NS = {"m": "http://bbn.com/marti/xml/bindings"}
META_PATH = RUNTIME_ID_DIR / "meta.json"


def _split_csv(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


def _validate_password(password: str) -> None:
    pw = str(password or "")
    problems: list[str] = []

    if len(pw) < 15:
        problems.append("min length 15")
    if re.search(r"\s", pw):
        problems.append("no whitespace")
    if not re.search(r"[A-Z]", pw):
        problems.append("missing uppercase")
    if not re.search(r"[a-z]", pw):
        problems.append("missing lowercase")
    if not re.search(r"[0-9]", pw):
        problems.append("missing digit")
    if not re.search(r"[^A-Za-z0-9]", pw):
        problems.append("missing special char")

    if problems:
        raise RuntimeError("takctl_admin_password does not meet policy: " + ", ".join(problems))


def _cert_env(cfg, sec) -> dict[str, str]:
    return {
        "COUNTRY": (cfg.get("cert_country", "SE") or "SE").strip(),
        "STATE": (cfg.get("cert_state", "") or "").strip(),
        "CITY": (cfg.get("cert_city", "") or "").strip(),
        "ORGANIZATION": (cfg.get("cert_organization", "TAK") or "TAK").strip(),
        "ORGANIZATIONAL_UNIT": (cfg.get("cert_organizational_unit", "") or "").strip(),
        "CAPASS": (sec.get("cert_capass", "") or "").strip(),
        "PASS": (sec.get("cert_pass", "") or "").strip(),
    }


def _ensure_runtime_dir() -> None:
    RUNTIME_ID_DIR.mkdir(parents=True, exist_ok=True)


def _existing_cert_paths(username: str) -> tuple[Path, Path] | None:
    candidates = [
        (
            CERTS_DIR / "04_USERS" / username / f"{username}.p12",
            CERTS_DIR / "04_USERS" / username / f"{username}.pem",
        ),
        (
            CERTS_DIR / f"{username}.p12",
            CERTS_DIR / f"{username}.pem",
        ),
    ]
    for p12, pem in candidates:
        if p12.exists() and pem.exists():
            return p12, pem
    return None


def _load_userauth_user(username: str) -> dict | None:
    if not USERAUTH_XML.exists():
        return None
    try:
        root = ET.parse(USERAUTH_XML).getroot()
    except Exception:
        return None

    for user in root.findall("m:User", XML_NS):
        ident = (user.attrib.get("identifier") or "").strip()
        if ident != username:
            continue
        return {
            "identifier": ident,
            "fingerprint": (user.attrib.get("fingerprint") or "").strip(),
            "role": (user.attrib.get("role") or "").strip(),
            "groups_rw": [x.text.strip() for x in user.findall("m:groupList", XML_NS) if (x.text or "").strip()],
            "groups_in": [x.text.strip() for x in user.findall("m:groupListIN", XML_NS) if (x.text or "").strip()],
            "groups_out": [x.text.strip() for x in user.findall("m:groupListOUT", XML_NS) if (x.text or "").strip()],
        }
    return None


def _wait_for_usermgr_ready(timeout_sec: int = 600, sleep_sec: int = 5) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if USERAUTH_XML.exists():
            print("[tak-admin-identity] UserAuthenticationFile.xml present")
            return
        print("[tak-admin-identity] waiting for /opt/tak/UserAuthenticationFile.xml ...")
        time.sleep(sleep_sec)
    raise RuntimeError("timed out waiting for /opt/tak/UserAuthenticationFile.xml")


def _ensure_inputs(cfg, sec) -> tuple[str, str, list[str], list[str], list[str]]:
    username = (cfg.get("takctl_admin_user", "admin") or "admin").strip() or "admin"
    password = (sec.get("takctl_admin_password", "") or "").strip()

    if not username:
        raise RuntimeError("missing takctl_admin_user")
    if not password:
        raise RuntimeError("missing takctl_admin_password")

    _validate_password(password)

    groups_rw = _split_csv(cfg.get("takctl_admin_groups_rw", ""))
    groups_in = _split_csv(cfg.get("takctl_admin_groups_in", ""))
    groups_out = _split_csv(cfg.get("takctl_admin_groups_out", ""))

    return username, password, groups_rw, groups_in, groups_out


def _ensure_user(cfg, sec) -> str:
    username, password, groups_rw, groups_in, groups_out = _ensure_inputs(cfg, sec)

    _wait_for_usermgr_ready()
    um = UserMgrService()
    um.preflight()
    um.user_set(
        username,
        password=password,
        groups=groups_rw or None,
        in_groups=groups_in or None,
        out_groups=groups_out or None,
    )
    print(f"[tak-admin-identity] ensure_user sync {username}")
    return username


def _ensure_cert(cfg, sec, username: str) -> tuple[Path, Path]:
    existing = _existing_cert_paths(username)
    if existing is not None:
        print(f"[tak-admin-identity] ensure_cert skip existing {existing[0]} {existing[1]}")
        return existing

    if not MAKECERT.exists():
        raise RuntimeError(f"missing makeCert.sh: {MAKECERT}")

    env = dict(_cert_env(cfg, sec))
    missing = [k for k in ("STATE", "CITY", "ORGANIZATIONAL_UNIT", "CAPASS", "PASS") if not env.get(k)]
    if missing:
        raise RuntimeError(f"missing cert config/secrets for makeCert.sh: {', '.join(missing)}")

    import subprocess

    cmd = (
        f"cd {CERTS_ROOT} && "
        f"export COUNTRY='{env['COUNTRY']}' "
        f"STATE='{env['STATE']}' "
        f"CITY='{env['CITY']}' "
        f"ORGANIZATION='{env['ORGANIZATION']}' "
        f"ORGANIZATIONAL_UNIT='{env['ORGANIZATIONAL_UNIT']}' "
        f"CAPASS='{env['CAPASS']}' "
        f"PASS='{env['PASS']}' && "
        f"./makeCert.sh client {username}"
    )
    subprocess.run(["sudo", "bash", "-lc", cmd], check=True, text=True)

    created = _existing_cert_paths(username)
    if created is None:
        raise RuntimeError(f"admin client cert not found after makeCert for {username}")
    print(f"[tak-admin-identity] ensure_cert create {created[0]} {created[1]}")
    return created


def _bind_user_to_cert(cfg, sec, cert_pem_path: Path) -> None:
    username, password, groups_rw, groups_in, groups_out = _ensure_inputs(cfg, sec)

    _wait_for_usermgr_ready()
    um = UserMgrService()
    um.preflight()
    um.user_set(
        username,
        password=password,
        certificate_path=str(cert_pem_path),
        groups=groups_rw or None,
        in_groups=groups_in or None,
        out_groups=groups_out or None,
    )
    print(f"[tak-admin-identity] bind_user_to_cert bind {username}")


def _install_runtime_identity(username: str, cert_p12_path: Path, cert_pem_path: Path) -> None:
    _ensure_runtime_dir()

    client_p12_dst = RUNTIME_ID_DIR / f"{username}.p12"
    trust_p12_dst = RUNTIME_ID_DIR / "truststore-root.p12"
    client_pem_dst = RUNTIME_ID_DIR / f"{username}.pem"
    client_key_dst = RUNTIME_ID_DIR / f"{username}.key"
    ca_pem_dst = RUNTIME_ID_DIR / "ca.pem"

    cert_key_path = cert_pem_path.with_suffix(".key")
    ca_pem_src = CERTS_DIR / "00_CA" / "ca.pem"

    if not cert_key_path.exists():
        raise RuntimeError(f"missing client key next to pem: {cert_key_path}")
    if not TRUSTSTORE_SRC.exists():
        raise RuntimeError(f"missing truststore source: {TRUSTSTORE_SRC}")
    if not ca_pem_src.exists():
        raise RuntimeError(f"missing CA pem: {ca_pem_src}")

    shutil.copy2(cert_p12_path, client_p12_dst)
    shutil.copy2(TRUSTSTORE_SRC, trust_p12_dst)
    shutil.copy2(cert_pem_path, client_pem_dst)
    shutil.copy2(cert_key_path, client_key_dst)
    shutil.copy2(ca_pem_src, ca_pem_dst)

    for path in (client_p12_dst, trust_p12_dst, client_pem_dst, client_key_dst, ca_pem_dst):
        shutil.chown(path, user="root", group="tak")
        path.chmod(0o640)

    META_PATH.write_text(
        json.dumps(
            {
                "ready": True,
                "username": username,
                "p12_path": str(client_p12_dst),
                "pem_path": str(client_pem_dst),
                "key_path": str(client_key_dst),
                "truststore_path": str(trust_p12_dst),
                "ca_pem_path": str(ca_pem_dst),
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"[tak-admin-identity] runtime identity installed under {RUNTIME_ID_DIR}")


class TakAdminIdentityAction:
    ID = SRC_ID

    def inspect(self, ctx) -> int:
        cfg = load_config()
        sec = load_secrets()

        username = (cfg.get("takctl_admin_user", "admin") or "admin").strip() or "admin"
        has_password = bool((sec.get("takctl_admin_password", "") or "").strip())
        existing = _existing_cert_paths(username)

        print("tak-admin-identity")
        print(f"  runtime_dir:    {RUNTIME_ID_DIR}")
        print(f"  username:       {username}")
        print(f"  password:       {'present' if has_password else 'missing'}")
        print(f"  existing_cert:  {str(existing[0]) if existing else '(missing)'}")
        print(f"  userauth:       {USERAUTH_XML}")
        return 0

    def apply(self, ctx) -> int:
        cfg = load_config()
        sec = load_secrets()

        save_runtime_config_view(cfg)
        save_runtime_secrets_view(sec)

        username = _ensure_user(cfg, sec)
        cert_p12_path, cert_pem_path = _ensure_cert(cfg, sec, username)
        _bind_user_to_cert(cfg, sec, cert_pem_path)
        _install_runtime_identity(username, cert_p12_path, cert_pem_path)

        print("[tak-admin-identity] done")
        return 0


ACTION = TakAdminIdentityAction()
