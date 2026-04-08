#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Set, Tuple
from pathlib import Path

from takctl.config import RuntimeConfig


@dataclass(frozen=True)
class OpenSSL:
    cfg: RuntimeConfig

    def _run(self, args: list[str], text: bool = True) -> str:
        out = subprocess.check_output(args, text=text, stderr=subprocess.STDOUT)
        return out

    def version(self) -> str:
        return self._run(["openssl", "version"]).strip()

    # ---------- Helpers ----------

    def gen_crl(self, out_crl_path: str) -> None:
        self._run([
            "openssl", "ca",
            "-config", str(Path(self.cfg.ca_dir) / "openssl-crl.cnf"),
            "-gencrl",
            "-out", out_crl_path,
        ])

    def _normalize_cert_to_pem(self, blob: str) -> str | None:
        """
        Normalize a certificate blob to canonical PEM.

        Accepts:
          - Proper PEM with newlines
          - One-line PEM (BEGIN...MII...END) with no newlines
          - Base64-only (no headers)

        Returns canonical PEM or None if it doesn't look like a cert.
        """
        s = (blob or "").strip()
        if not s:
            return None

        if "BEGIN CERTIFICATE" in s:
            b64 = s.replace("-----BEGIN CERTIFICATE-----", "").replace(
                "-----END CERTIFICATE-----", ""
            )
            b64 = "".join(b64.split())
        else:
            # base64-only
            b64 = "".join(s.split())

        # quick sanity: base64 chars only-ish
        if not b64 or re.search(r"[^A-Za-z0-9+/=]", b64):
            return None

        lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
        return (
            "-----BEGIN CERTIFICATE-----\n"
            + "\n".join(lines)
            + "\n-----END CERTIFICATE-----\n"
        )

    # ---------- Public API used by takctl ----------

    def cert_serial_subject(self, pem: str) -> Tuple[str | None, str | None]:
        """
        Return (serial_hex, subject) from a cert blob stored in DB.

        Never raises: returns (None, None) on failure.
        """
        norm = self._normalize_cert_to_pem(pem)
        if not norm:
            return (None, None)

        path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tf:
                path = tf.name
                tf.write(norm)

            try:
                out = self._run(
                    ["openssl", "x509", "-in", path, "-noout", "-serial", "-subject"]
                )
            except subprocess.CalledProcessError:
                return (None, None)
            except Exception:
                return (None, None)
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        serial = None
        subj = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("serial="):
                serial = line.split("=", 1)[1].strip()
            elif line.startswith("subject="):
                subj = line.split("=", 1)[1].strip()

        return (serial, subj)

    def crl_revoked_serials(self, crl_path: str) -> Set[str]:
        """
        Parse a CRL file and return a set of revoked cert serials (uppercase hex).

        Supports PEM CRL and DER CRL. Never raises; returns empty set on failure.
        """
        if not crl_path or not os.path.exists(crl_path):
            return set()

        # Try PEM first
        for inform in ("PEM", "DER"):
            try:
                out = self._run(
                    ["openssl", "crl", f"-inform", inform, "-in", crl_path, "-noout", "-text"]
                )
                break
            except Exception:
                out = None
        if not out:
            return set()

        serials: set[str] = set()

        # OpenSSL text usually includes lines like:
        #   Serial Number: 36:32:B0:3F
        # or:
        #   Serial Number: 3632B03F
        for line in out.splitlines():
            line = line.strip()
            if "Serial Number:" in line:
                s = line.split("Serial Number:", 1)[1].strip()
                s = s.replace(":", "").replace(" ", "").upper()
                if s:
                    serials.add(s)

        return serials
