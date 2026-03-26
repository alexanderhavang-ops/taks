from __future__ import annotations

import logging
import secrets
import shutil
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

from takctl.config import load_config, load_secrets
from takctl.config_store import save_runtime_config_view, save_runtime_secrets_view
from takctl.services.usermgr import UserMgrService

log = logging.getLogger(__name__)

SRC_ID = "martine-identity"

RUNTIME_ID_DIR = Path("/opt/tak/tools/martine/runtime/identity")
CERTS_ROOT = Path("/opt/tak/certs")
CERTS_DIR = Path("/opt/tak/certs/files")
MAKECERT = Path("/opt/tak/certs/makeCert.sh")
TRUSTSTORE_SRC = Path("/opt/tak/certs/files/01_TRUST/truststore-root.p12")
USERAUTH_XML = Path("/opt/tak/UserAuthenticationFile.xml")
XML_NS = {"m": "http://bbn.com/marti/xml/bindings"}


def _strong_password(n: int = 20) -> str:
    uppers = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lowers = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    specials = r"-_!@#$%^&*(){}[]+=~`|:;<>,./?"
    alphabet = uppers + lowers + digits + specials
    chars = [
        secrets.choice(uppers),
        secrets.choice(lowers),
        secrets.choice(digits),
        secrets.choice(specials),
    ]
    while len(chars) < max(n, 15):
        chars.append(secrets.choice(alphabet))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _split_groups(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


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


def _groups_match(actual: list[str], wanted: list[str]) -> bool:
    return sorted(actual) == sorted(wanted)


def _ensure_secrets() -> tuple[str, str, str]:
    sec = load_secrets()

    changed = False
    martine_user_password = (sec.get("martine_user_password", "") or "").strip()
    martine_client_p12_pass = (sec.get("martine_client_p12_pass", "") or "").strip()
    martine_truststore_p12_pass = (sec.get("martine_truststore_p12_pass", "") or "").strip()

    if not martine_user_password:
        martine_user_password = _strong_password(20)
        changed = True

    if not martine_client_p12_pass:
        martine_client_p12_pass = (
            (sec.get("user_key_pass", "") or "").strip()
            or (sec.get("onboarding_client_p12_default_pass", "") or "").strip()
            or (sec.get("ca_signing_p12_pass", "") or "").strip()
            or (sec.get("cert_pass", "") or "").strip()
        )
        changed = True

    if not martine_truststore_p12_pass:
        martine_truststore_p12_pass = (
            (sec.get("cert_capass", "") or "").strip()
            or (sec.get("ca_signing_p12_pass", "") or "").strip()
        )
        changed = True

    if changed:
        sec.set("martine_user_password", martine_user_password, component="martine")
        sec.set("martine_client_p12_pass", martine_client_p12_pass, component="martine")
        sec.set("martine_truststore_p12_pass", martine_truststore_p12_pass, component="martine")
        save_runtime_secrets_view(sec)

    return martine_user_password, martine_client_p12_pass, martine_truststore_p12_pass


def _ensure_user(cfg, user_password: str) -> None:
    username = (cfg.get("martine_username", "martine") or "martine").strip() or "martine"
    groups_rw = _split_groups(cfg.get("martine_groups_rw", ""))
    groups_in = _split_groups(cfg.get("martine_groups_in", ""))
    groups_out = _split_groups(cfg.get("martine_groups_out", ""))

    current = _load_userauth_user(username)
    if current is not None:
        if (
            _groups_match(current["groups_rw"], groups_rw)
            and _groups_match(current["groups_in"], groups_in)
            and _groups_match(current["groups_out"], groups_out)
        ):
            print(f"[martine-identity] ensure_user skip xml-ok")
            return

        um = UserMgrService()
        um.preflight()
        um.user_set(
            username,
            groups=groups_rw or None,
            in_groups=groups_in or None,
            out_groups=groups_out or None,
        )
        print(f"[martine-identity] ensure_user update-groups")
        return

    um = UserMgrService()
    um.preflight()
    um.user_set(
        username,
        password=user_password,
        groups=groups_rw or None,
        in_groups=groups_in or None,
        out_groups=groups_out or None,
    )
    print(f"[martine-identity] ensure_user create")


def _ensure_cert(cfg, sec) -> tuple[Path, Path]:
    username = (cfg.get("martine_username", "martine") or "martine").strip() or "martine"

    existing = _existing_cert_paths(username)
    if existing is not None:
        print(f"[martine-identity] ensure_cert skip existing {existing[0]} {existing[1]}")
        return existing

    if not MAKECERT.exists():
        raise RuntimeError(f"missing makeCert.sh: {MAKECERT}")

    env = dict(_cert_env(cfg, sec))
    missing = [k for k in ("STATE", "CITY", "ORGANIZATIONAL_UNIT", "CAPASS", "PASS") if not env.get(k)]
    if missing:
        raise RuntimeError(f"missing cert config/secrets for makeCert.sh: {', '.join(missing)}")

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
        raise RuntimeError(f"martine client cert not found after makeCert for {username}")
    print(f"[martine-identity] ensure_cert create {created[0]} {created[1]}")
    return created


def _bind_user_to_cert(cfg, cert_pem_path: Path, user_password: str) -> None:
    username = (cfg.get("martine_username", "martine") or "martine").strip() or "martine"
    current = _load_userauth_user(username)
    if current is not None and (current.get("fingerprint") or "").strip():
        print(f"[martine-identity] bind_user_to_cert skip fingerprint-present")
        return

    groups_rw = _split_groups(cfg.get("martine_groups_rw", ""))
    groups_in = _split_groups(cfg.get("martine_groups_in", ""))
    groups_out = _split_groups(cfg.get("martine_groups_out", ""))

    um = UserMgrService()
    um.preflight()
    um.user_set(
        username,
        password=user_password,
        certificate_path=str(cert_pem_path),
        groups=groups_rw or None,
        in_groups=groups_in or None,
        out_groups=groups_out or None,
    )
    print(f"[martine-identity] bind_user_to_cert bind")


def _install_runtime_identity(cfg, cert_p12_path: Path, cert_pem_path: Path) -> None:
    _ensure_runtime_dir()

    client_p12_dst = RUNTIME_ID_DIR / "client.p12"
    trust_p12_dst = RUNTIME_ID_DIR / "truststore-root.p12"
    client_pem_dst = RUNTIME_ID_DIR / "client.pem"
    client_key_dst = RUNTIME_ID_DIR / "client.key"
    ca_pem_dst = RUNTIME_ID_DIR / "ca.pem"

    cert_key_path = cert_pem_path.with_suffix(".key")
    ca_pem_src = CERTS_DIR / "00_CA" / "ca.pem"

    if not cert_key_path.exists():
        raise RuntimeError(f"martine client key not found: {cert_key_path}")
    if not ca_pem_src.exists():
        raise RuntimeError(f"martine ca pem not found: {ca_pem_src}")

    shutil.copy2(cert_p12_path, client_p12_dst)
    shutil.copy2(TRUSTSTORE_SRC, trust_p12_dst)
    shutil.copy2(cert_pem_path, client_pem_dst)
    shutil.copy2(cert_key_path, client_key_dst)
    shutil.copy2(ca_pem_src, ca_pem_dst)

    subprocess.run(["sudo", "mkdir", "-p", str(RUNTIME_ID_DIR)], check=True)
    subprocess.run(["sudo", "chown", "-R", "tak:tak", str(RUNTIME_ID_DIR)], check=True)
    subprocess.run(["sudo", "find", str(RUNTIME_ID_DIR), "-type", "d", "-exec", "chmod", "2750", "{}", ";"], check=True)
    subprocess.run(["sudo", "find", str(RUNTIME_ID_DIR), "-type", "f", "-exec", "chmod", "0640", "{}", ";"], check=True)

    cfg2 = load_config()
    changed = False
    if cfg2.get("martine_client_p12_path", "") != str(client_p12_dst):
        cfg2.set("martine_client_p12_path", str(client_p12_dst), component="martine")
        changed = True
    if cfg2.get("martine_truststore_p12_path", "") != str(trust_p12_dst):
        cfg2.set("martine_truststore_p12_path", str(trust_p12_dst), component="martine")
        changed = True
    if changed:
        save_runtime_config_view(cfg2)


class Action:
    ID = SRC_ID

    def inspect(self, ctx) -> int:
        self.verify(ctx)
        return 0

    def apply(self, ctx) -> int:
        cfg = load_config()
        user_password, _client_p12_pass, _truststore_p12_pass = _ensure_secrets()
        sec = load_secrets()

        _ensure_user(cfg, user_password)
        cert_p12_path, cert_pem_path = _ensure_cert(cfg, sec)
        _bind_user_to_cert(cfg, cert_pem_path, user_password)
        _install_runtime_identity(cfg, cert_p12_path, cert_pem_path)
        return 0

    def verify(self, ctx) -> None:
        cfg = load_config()
        username = (cfg.get("martine_username", "martine") or "martine").strip() or "martine"
        client_p12 = Path(cfg.get("martine_client_p12_path", "/opt/tak/tools/martine/runtime/identity/client.p12"))
        trust_p12 = Path(cfg.get("martine_truststore_p12_path", "/opt/tak/tools/martine/runtime/identity/truststore-root.p12"))

        if not client_p12.exists():
            raise RuntimeError(f"missing martine client p12: {client_p12}")
        if not trust_p12.exists():
            raise RuntimeError(f"missing martine truststore p12: {trust_p12}")

        current = _load_userauth_user(username)
        if current is None:
            raise RuntimeError(f"user not found in UserAuthenticationFile.xml: {username}")


ACTION = Action()
