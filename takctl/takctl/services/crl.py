from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


_SERIAL_RE = re.compile(r"Serial Number:\s*([0-9A-Fa-f]+)")


class CrlError(RuntimeError):
    pass


def _which(prog: str) -> Optional[str]:
    return shutil.which(prog)


def _run(cmd: list[str], *, check: bool = True) -> str:
    """
    Run a command and return stdout+stderr as text.
    """
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout)
    return p.stdout


def _atomic_replace(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _parse_crl_serials(crl_path: Path) -> list[str]:
    if not crl_path.exists():
        return []
    out = _run(["openssl", "crl", "-in", str(crl_path), "-noout", "-text"], check=True)
    serials = _SERIAL_RE.findall(out)
    return [s.upper() for s in serials]


def _utc_mtime(path: Path) -> str:
    st = path.stat()
    dt = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    return dt.isoformat()


def _ensure_ca_db_files(ca_dir: Path, *, force: bool) -> None:
    """
    OpenSSL CA database files used by openssl ca -revoke / -gencrl.

    We keep this small and predictable:
      - crl_index.txt
      - crl_index.txt.attr   (unique_subject = no)
      - crlnumber            (initialized to 1000 if missing or force)
    """
    ca_dir.mkdir(parents=True, exist_ok=True)

    index = ca_dir / "crl_index.txt"
    attr = ca_dir / "crl_index.txt.attr"
    crlnumber = ca_dir / "crlnumber"

    if force:
        index.write_text("", encoding="utf-8")
        attr.write_text("unique_subject = no\n", encoding="utf-8")
        crlnumber.write_text("1000\n", encoding="utf-8")
        return

    if not index.exists():
        index.write_text("", encoding="utf-8")
    if not attr.exists():
        attr.write_text("unique_subject = no\n", encoding="utf-8")
    if not crlnumber.exists():
        crlnumber.write_text("1000\n", encoding="utf-8")


def _get_revoked_cert_pems_from_db(ctx) -> list[str]:
    """
    TAK 5.6 uses public.certificate.
    "revoked" == revocation_date IS NOT NULL.
    Column 'certificate' is a PEM (text).
    """
    sql = """
        SELECT certificate
        FROM public.certificate
        WHERE revocation_date IS NOT NULL
    """
    rows = ctx.db.fetchall(sql)
    return [r[0] for r in rows if r and r[0]]


def _db_schema_preflight(ctx) -> None:
    """
    Validate DB connectivity + expected schema.
    Keep this fast and explicit so WebUI shows clear errors.
    """
    try:
        # Connectivity
        u = ctx.db.scalar("SELECT current_user")
    except Exception as e:
        raise CrlError(f"DB connection failed: {e}") from e

    # Table exists?
    t = ctx.db.scalar(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='certificate'"
    )
    if str(t).strip() != "1":
        raise CrlError("DB schema missing required table: public.certificate")

    # Required columns?
    try:
        rows = ctx.db.fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='certificate'"
        )
    except Exception as e:
        raise CrlError(f"DB schema inspection failed: {e}") from e

    cols = {str(r[0]) for r in rows if r and r[0]}
    need = {"certificate", "revocation_date"}
    missing = sorted(need - cols)
    if missing:
        raise CrlError(f"DB schema missing columns in public.certificate: {', '.join(missing)}")


def crl_preflight(ctx) -> None:
    """
    Fast, high-signal validation before rebuild.
    Order matters: fail on the most common / user-actionable issues first.
    """
    # openssl present?
    if not _which("openssl"):
        raise CrlError("openssl not found in PATH")

    ca_dir = Path(ctx.cfg.ca_dir)
    conf = ca_dir / "openssl-crl.cnf"
    if not conf.exists():
        raise CrlError(f"Missing OpenSSL CRL config: {conf}")
    if not os.access(conf, os.R_OK):
        raise CrlError(f"OpenSSL CRL config not readable: {conf}")

    # DB sanity (WebUI-safe: tells you immediately if user/table/cols are wrong)
    _db_schema_preflight(ctx)

    # signer helper sanity (only required when ca.key not readable by current user)
    helper = getattr(ctx.cfg, "crl_sign_helper", "") or ""
    key = ca_dir / "ca.key"
    if not os.access(key, os.R_OK):
        if not helper:
            raise CrlError(f"CA key not readable ({key}); configure crl_sign_helper for root signing")
        hp = Path(helper)
        if not hp.exists():
            raise CrlError(f"Missing signer helper: {hp}")
        if not os.access(hp, os.X_OK):
            raise CrlError(f"Signer helper not executable: {hp}")


def _revoke_cert_pem_into_openssl_db(ctx, cert_pem: str) -> None:
    ca_dir = Path(ctx.cfg.ca_dir)
    conf = ca_dir / "openssl-crl.cnf"
    if not conf.exists():
        raise FileNotFoundError(f"Missing OpenSSL CRL config: {conf}")

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem") as tf:
        tf.write(cert_pem)
        cert_path = tf.name

    try:
        _run(["openssl", "ca", "-config", str(conf), "-revoke", cert_path], check=True)
    finally:
        try:
            os.unlink(cert_path)
        except FileNotFoundError:
            pass


def _revoke_via_helper(ctx, revoked_pems: list[str]) -> None:
    """
    Send PEMs to helper (runs as root via sudoers) which updates the OpenSSL index.
    """
    helper = getattr(ctx.cfg, "crl_sign_helper", "") or ""
    if not helper:
        raise CrlError("crl_sign_helper not configured")

    p = subprocess.run(
        [helper, ctx.cfg.ca_dir],
        input="".join(revoked_pems),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0:
        raise CrlError(f"Signer helper failed:\n{p.stdout}")
    # helper prints something like OK: revoked N cert(s)


def crl_status(ctx) -> dict:
    crl_path = Path(ctx.cfg.crl_path)
    info: dict = {"crl_path": str(crl_path), "exists": crl_path.exists()}

    if not crl_path.exists():
        info.update({"mtime": None, "revoked_serials": 0, "sample_serials": []})
        return info

    serials = _parse_crl_serials(crl_path)
    info.update(
        {
            "mtime": _utc_mtime(crl_path),
            "revoked_serials": len(serials),
            "sample_serials": serials[:10],
        }
    )
    return info


def rebuild_crl_from_db(ctx, *, force: bool = True) -> None:
    """
    Authoritative rebuild of CRL based on revoked certs in Postgres.

    Steps:
      0) Preflight checks (explicit errors)
      1) Ensure/seed OpenSSL CA database files (force empties)
      2) Pull revoked cert PEMs from DB
      3) Populate OpenSSL index:
           - if ca.key readable: run openssl ca -revoke for each
           - else: call signer helper (root) once
      4) openssl ca -gencrl to generate CRL
      5) Atomic replace of ctx.cfg.crl_path
    """
    crl_preflight(ctx)

    ca_dir = Path(ctx.cfg.ca_dir)
    conf = ca_dir / "openssl-crl.cnf"

    _ensure_ca_db_files(ca_dir, force=force)
    revoked_pems = _get_revoked_cert_pems_from_db(ctx)

    key = ca_dir / "ca.key"
    if os.access(key, os.R_OK):
        for pem in revoked_pems:
            _revoke_cert_pem_into_openssl_db(ctx, pem)
    else:
        _revoke_via_helper(ctx, revoked_pems)

    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".crl") as tf:
        tmp_crl = Path(tf.name)

    try:
        _run(["openssl", "ca", "-config", str(conf), "-gencrl", "-out", str(tmp_crl)], check=True)
        _atomic_replace(tmp_crl, Path(ctx.cfg.crl_path))
    finally:
        try:
            tmp_crl.unlink(missing_ok=True)
        except Exception:
            pass

