"""Private orchestrator CA for node DevOps MCP mutual TLS.

The CA signing key stays on the orchestrator and is never bundled.
Each bundle receives a freshly issued, node-specific server leaf.
"""
from __future__ import annotations

import fcntl
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from orchestrator_core.config import load_orch_config


def _pki_dir() -> Path:
    return Path(os.environ.get("TAKS_DEVOPS_PKI_DIR", str(Path(load_orch_config().paths.state_dir) / "devops-pki")))


PKI_DIR = _pki_dir()
FQDN = re.compile(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


def _openssl(*args: str) -> None:
    subprocess.run(["openssl", *map(str, args)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45)


def _valid_cert(cert: Path, ca: Path | None = None) -> bool:
    try:
        _openssl("x509", "-in", str(cert), "-noout", "-checkend", "604800")
        if ca is not None:
            _openssl("verify", "-CAfile", str(ca), str(cert))
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _matches(cert: Path, key: Path) -> bool:
    try:
        cert_pub = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert), "-pubkey", "-noout"], timeout=15)
        key_pub = subprocess.check_output(
            ["openssl", "pkey", "-in", str(key), "-pubout"], timeout=15)
        return cert_pub == key_pub
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _issue(ca: Path, ca_key: Path, cert: Path, key: Path,
           common_name: str, *, client: bool) -> None:
    with tempfile.TemporaryDirectory(prefix=".issue-", dir=PKI_DIR) as td:
        work = Path(td)
        csr = work / "request.csr"
        tmp_key = work / "leaf.key"
        tmp_cert = work / "leaf.crt"
        ext = work / "extensions.cnf"
        usage = "clientAuth" if client else "serverAuth"
        san = "" if client else f"subjectAltName=DNS:{common_name}\n"
        ext.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            f"extendedKeyUsage={usage}\n{san}", encoding="ascii")
        _openssl("req", "-new", "-newkey", "rsa:3072", "-nodes",
                 "-keyout", str(tmp_key), "-out", str(csr),
                 "-subj", f"/CN={common_name}")
        _openssl("x509", "-req", "-in", str(csr),
                 "-CA", str(ca), "-CAkey", str(ca_key),
                 "-set_serial", "0x" + secrets.token_hex(16), "-out", str(tmp_cert),
                 "-days", "90", "-sha256", "-extfile", str(ext))
        if not _valid_cert(tmp_cert, ca) or not _matches(tmp_cert, tmp_key):
            raise RuntimeError("issued DevOps certificate failed validation")
        os.chmod(tmp_key, 0o600)
        os.chmod(tmp_cert, 0o644)
        os.replace(tmp_key, key)
        os.replace(tmp_cert, cert)


def _ensure_authority() -> tuple[Path, Path]:
    PKI_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PKI_DIR, 0o700)
    ca = PKI_DIR / "ca.crt"
    key = PKI_DIR / "ca.key"
    client = PKI_DIR / "client.crt"
    client_key = PKI_DIR / "client.key"
    with (PKI_DIR / ".issue.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ca.exists() != key.exists():
            raise RuntimeError("incomplete DevOps CA; refusing automatic replacement")
        if not ca.exists():
            with tempfile.TemporaryDirectory(prefix=".ca-", dir=PKI_DIR) as td:
                tmp_ca, tmp_key = Path(td) / "ca.crt", Path(td) / "ca.key"
                _openssl("req", "-x509", "-newkey", "rsa:4096", "-nodes",
                         "-keyout", str(tmp_key), "-out", str(tmp_ca),
                         "-days", "3650", "-sha256", "-subj", "/CN=TAKS DevOps Orchestrator CA",
                         "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                         "-addext", "keyUsage=critical,keyCertSign,cRLSign")
                os.chmod(tmp_key, 0o600)
                os.chmod(tmp_ca, 0o644)
                os.replace(tmp_key, key)
                os.replace(tmp_ca, ca)
        if not _valid_cert(ca) or not _matches(ca, key):
            raise RuntimeError("DevOps CA invalid or expiring; rotate explicitly")
        if client.exists() != client_key.exists():
            raise RuntimeError("incomplete DevOps client identity")
        if not client.exists() or not _valid_cert(client, ca) or not _matches(client, client_key):
            _issue(ca, key, client, client_key, "taks-orchestrator", client=True)
        return ca, key


def provision_node_devops_tls(bundle_root: Path, node_fqdn: str) -> dict[str, object]:
    fqdn = node_fqdn.strip().lower()
    if not FQDN.fullmatch(fqdn) or "." not in fqdn or ".." in fqdn:
        raise ValueError("invalid node FQDN for DevOps TLS")
    if shutil.which("openssl") is None:
        raise RuntimeError("openssl required to issue DevOps mTLS identities")
    ca, ca_key = _ensure_authority()
    dest = bundle_root / "install" / "devops-mtls"
    dest.mkdir(parents=True, exist_ok=True)
    node_cert = dest / "node.crt"
    node_key = dest / "node.key"
    shutil.copyfile(ca, dest / "ca.crt")
    _issue(ca, ca_key, node_cert, node_key, f"devops.{fqdn}", client=False)
    os.chmod(node_key, 0o600)
    return {"generated": "install/devops-mtls", "kind": "devops_mtls",
            "files": 3, "fqdn": f"devops.{fqdn}"}
