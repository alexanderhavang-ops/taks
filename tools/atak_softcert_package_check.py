#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


@dataclasses.dataclass
class CheckResult:
    status: str  # PASS, WARN, FAIL, INFO
    name: str
    detail: str


class Reporter:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def add(self, status: str, name: str, detail: str) -> None:
        self.results.append(CheckResult(status=status, name=name, detail=detail.rstrip()))

    def has_failures(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)

    def render_text(self) -> str:
        lines: list[str] = []
        for r in self.results:
            icon = {
                "PASS": "[PASS]",
                "WARN": "[WARN]",
                "FAIL": "[FAIL]",
                "INFO": "[INFO]",
            }.get(r.status, f"[{r.status}]")
            lines.append(f"{icon} {r.name}")
            for part in r.detail.splitlines():
                lines.append(f"       {part}")
        return "\n".join(lines)

    def render_json(self) -> str:
        return json.dumps([dataclasses.asdict(r) for r in self.results], indent=2, ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: list[str], *, input_text: str | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def openssl_available() -> bool:
    return shutil.which("openssl") is not None


def require_openssl() -> None:
    if not openssl_available():
        raise RuntimeError("openssl not found in PATH")


def load_zip_from_url(url: str, dst: Path) -> None:
    with urllib.request.urlopen(url) as r:  # nosec - caller supplies URL intentionally
        dst.write_bytes(r.read())


def detect_manifest_name(names: list[str]) -> str | None:
    candidates = [
        "MANIFEST/manifest.xml",
        "manifest.xml",
        "MANIFEST.xml",
    ]
    for c in candidates:
        if c in names:
            return c
    for n in names:
        if n.lower().endswith("manifest.xml"):
            return n
    return None


def parse_pref_entries(pref_xml: str) -> dict[str, str]:
    root = ET.fromstring(pref_xml)
    out: dict[str, str] = {}
    for pref in root.findall("./preference"):
        pref_name = pref.attrib.get("name", "")
        for entry in pref.findall("./entry"):
            key = entry.attrib.get("key")
            if not key:
                continue
            value = (entry.text or "").strip()
            # keep both raw key and pref-scoped key for convenience
            out[key] = value
            out[f"{pref_name}:{key}"] = value
    return out


def extract_pkcs12_cert(
    p12_path: Path,
    out_pem: Path,
    password: str,
    *,
    use_legacy: bool,
    kind: str,
) -> subprocess.CompletedProcess[str]:
    require_openssl()
    cmd = ["openssl", "pkcs12"]
    if use_legacy:
        cmd.append("-legacy")
    cmd += ["-in", str(p12_path), "-nokeys", f"-{'cacerts' if kind == 'ca' else 'clcerts'}", "-out", str(out_pem), "-passin", f"pass:{password}"]
    return run_cmd(cmd)


def test_pkcs12_password(p12_path: Path, password: str, *, use_legacy: bool) -> subprocess.CompletedProcess[str]:
    require_openssl()
    cmd = ["openssl", "pkcs12"]
    if use_legacy:
        cmd.append("-legacy")
    cmd += ["-in", str(p12_path), "-nokeys", "-passin", f"pass:{password}"]
    return run_cmd(cmd)


def x509_subject_issuer(cert_path: Path) -> tuple[str, str]:
    require_openssl()
    proc = run_cmd(["openssl", "x509", "-in", str(cert_path), "-noout", "-subject", "-issuer"], check=True)
    subject = ""
    issuer = ""
    for line in proc.stdout.splitlines():
        if line.startswith("subject="):
            subject = line.split("=", 1)[1].strip()
        elif line.startswith("issuer="):
            issuer = line.split("=", 1)[1].strip()
    return subject, issuer


def x509_fingerprint(cert_path: Path) -> str:
    proc = run_cmd(["openssl", "x509", "-in", str(cert_path), "-noout", "-fingerprint", "-sha256"], check=True)
    line = proc.stdout.strip()
    return line.split("=", 1)[1].replace(":", "").lower() if "=" in line else line.lower()


def verify_chain(ca_pem: Path, client_pem: Path, *, sslclient: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["openssl", "verify", "-show_chain"]
    if sslclient:
        cmd += ["-purpose", "sslclient"]
    cmd += ["-CAfile", str(ca_pem), str(client_pem)]
    return run_cmd(cmd)


def extract_cn(name: str) -> str | None:
    m = re.search(r"(?:^|,\s*)CN\s*=\s*([^,]+)", name)
    return m.group(1).strip() if m else None


def autodetect_file(candidates: list[Path]) -> Path | None:
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def iter_xml_hits(root: ET.Element, needle: str) -> list[str]:
    needle_l = needle.lower()
    hits: list[str] = []
    for elem in root.iter():
        for k, v in elem.attrib.items():
            if needle_l in str(v).lower():
                hits.append(f"<{elem.tag} {k}={v!r}>")
        txt = (elem.text or "").strip()
        if txt and needle_l in txt.lower():
            hits.append(f"<{elem.tag}> text={txt!r}")
    return hits


def compare_against_local_cert_dir(
    rep: Reporter,
    cert_dir: Path,
    package_ca_p12: Path,
    package_client_p12: Path,
    package_ca_pem: Path,
) -> None:
    if not cert_dir.exists() or not cert_dir.is_dir():
        rep.add("WARN", "local cert dir", f"not found: {cert_dir}")
        return

    rep.add("INFO", "local cert dir", f"using {cert_dir}")

    local_ca_p12 = cert_dir / "caCert.p12"
    local_client_p12 = cert_dir / "clientCert.p12"

    if local_ca_p12.exists():
        same = sha256_file(local_ca_p12) == sha256_file(package_ca_p12)
        rep.add(
            "PASS" if same else "WARN",
            "compare local caCert.p12",
            f"local={local_ca_p12}\npackage_sha256={sha256_file(package_ca_p12)}\nlocal_sha256={sha256_file(local_ca_p12)}",
        )
    else:
        rep.add("INFO", "compare local caCert.p12", f"not present at {local_ca_p12}")

    if local_client_p12.exists():
        same = sha256_file(local_client_p12) == sha256_file(package_client_p12)
        rep.add(
            "PASS" if same else "WARN",
            "compare local clientCert.p12",
            f"local={local_client_p12}\npackage_sha256={sha256_file(package_client_p12)}\nlocal_sha256={sha256_file(local_client_p12)}",
        )
    else:
        rep.add("INFO", "compare local clientCert.p12", f"not present at {local_client_p12}")

    pem_candidates = sorted(list(cert_dir.glob("*.pem")) + list(cert_dir.glob("*.crt")) + list(cert_dir.glob("*.cer")))
    if not pem_candidates:
        rep.add("INFO", "local CA fingerprint search", "no local PEM/CRT/CER candidates found")
        return

    package_fp = x509_fingerprint(package_ca_pem)
    matches: list[str] = []
    for pem in pem_candidates:
        proc = run_cmd(["openssl", "x509", "-in", str(pem), "-noout", "-fingerprint", "-sha256"])
        if proc.returncode != 0:
            continue
        fp_line = proc.stdout.strip()
        fp = fp_line.split("=", 1)[1].replace(":", "").lower() if "=" in fp_line else fp_line.lower()
        if fp == package_fp:
            matches.append(str(pem))
    if matches:
        rep.add("PASS", "local CA fingerprint search", f"package CA matches local file(s):\n" + "\n".join(matches))
    else:
        rep.add("WARN", "local CA fingerprint search", f"no local PEM/CRT/CER fingerprint match for package CA under {cert_dir}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check a TAK soft-cert onboarding package ZIP URL or local ZIP file.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python3 atak_softcert_package_check.py \
                --zip-url 'https://host/api/onboarding/cards/.../packages/atak/soft-cert/package.zip'

              python3 atak_softcert_package_check.py \
                --zip-url 'https://host/api/onboarding/cards/.../packages/atak/soft-cert/package.zip' \
                --cert-dir /opt/tak/certs/files \
                --userauth /opt/tak/UserAuthenticationFile.xml \
                --expected-user alexander.havang \
                --expected-callsign EAPQ1
            """
        ),
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip-url", help="URL to package.zip")
    src.add_argument("--zip-file", help="Path to a local package.zip")
    ap.add_argument("--cert-dir", help="Local cert directory to compare against")
    ap.add_argument("--userauth", help="Path to UserAuthenticationFile.xml")
    ap.add_argument("--expected-user", help="Username/email/etc to search for in UserAuthenticationFile.xml")
    ap.add_argument("--expected-callsign", help="Expected callsign to compare against config.pref and search in UserAuthenticationFile.xml")
    ap.add_argument("--expected-host", help="Expected host; default derives from --zip-url if possible")
    ap.add_argument("--keep-temp", action="store_true", help="Keep temp dir and print its path")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    rep = Reporter()
    temp_ctx = tempfile.TemporaryDirectory(prefix="atak-softcert-check-")
    temp_root = Path(temp_ctx.name)

    try:
        zip_path = temp_root / "package.zip"
        source_desc = ""
        if args.zip_url:
            source_desc = args.zip_url
            load_zip_from_url(args.zip_url, zip_path)
        else:
            source_desc = args.zip_file
            shutil.copy2(Path(args.zip_file), zip_path)

        rep.add("INFO", "input", f"source={source_desc}\nlocal_copy={zip_path}")

        if not zipfile.is_zipfile(zip_path):
            rep.add("FAIL", "zip", "input is not a valid ZIP archive")
            print(rep.render_json() if args.json else rep.render_text())
            return 1

        rep.add("PASS", "zip", f"valid ZIP archive\nsize={zip_path.stat().st_size} bytes\nsha256={sha256_file(zip_path)}")

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            rep.add("INFO", "zip entries", "\n".join(names))

            manifest_name = detect_manifest_name(names)
            if not manifest_name:
                rep.add("FAIL", "manifest", "manifest.xml not found")
                print(rep.render_json() if args.json else rep.render_text())
                return 1

            manifest_xml = zf.read(manifest_name).decode("utf-8", errors="replace")
            try:
                manifest_root = ET.fromstring(manifest_xml)
            except ET.ParseError as e:
                rep.add("FAIL", "manifest parse", str(e))
                print(rep.render_json() if args.json else rep.render_text())
                return 1

            version = manifest_root.attrib.get("version")
            params = {
                p.attrib.get("name", ""): p.attrib.get("value", "")
                for p in manifest_root.findall("./Configuration/Parameter")
            }
            entries = [c.attrib.get("zipEntry", "") for c in manifest_root.findall("./Contents/Content")]
            missing_entries = [e for e in entries if e and e not in names]

            if version == "2":
                rep.add("PASS", "manifest version", f"version={version}")
            else:
                rep.add("WARN", "manifest version", f"expected 2, got {version!r}")
            rep.add("INFO", "manifest params", json.dumps(params, indent=2, ensure_ascii=False))

            if missing_entries:
                rep.add("FAIL", "manifest contents", "missing ZIP entries referenced by manifest:\n" + "\n".join(missing_entries))
            else:
                rep.add("PASS", "manifest contents", "all manifest zipEntry values exist in the archive")

            pref_name = next((n for n in names if n.lower().endswith(".pref")), None)
            if not pref_name:
                rep.add("FAIL", "config.pref", "no .pref file found in package")
                print(rep.render_json() if args.json else rep.render_text())
                return 1

            pref_xml = zf.read(pref_name).decode("utf-8", errors="replace")
            try:
                pref_entries = parse_pref_entries(pref_xml)
                rep.add("PASS", "config.pref parse", f"parsed {pref_name}")
            except ET.ParseError as e:
                rep.add("FAIL", "config.pref parse", f"{pref_name}: {e}")
                print(rep.render_json() if args.json else rep.render_text())
                return 1

            rep.add(
                "INFO",
                "config.pref keys",
                json.dumps({k: v for k, v in pref_entries.items() if ":" not in k}, indent=2, ensure_ascii=False),
            )

            ca_entry = next((n for n in names if n.endswith("/caCert.p12") or n.endswith("caCert.p12")), None)
            client_entry = next((n for n in names if n.endswith("/clientCert.p12") or n.endswith("clientCert.p12")), None)
            if not ca_entry or not client_entry:
                rep.add("FAIL", "package certs", f"ca_entry={ca_entry!r}\nclient_entry={client_entry!r}")
                print(rep.render_json() if args.json else rep.render_text())
                return 1

            work_dir = temp_root / "unz"
            work_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(work_dir)

        ca_p12 = work_dir / ca_entry
        client_p12 = work_dir / client_entry
        ca_password = pref_entries.get("caPassword", "")
        client_password = pref_entries.get("clientPassword", "")
        connect_string = pref_entries.get("connectString0", "")
        ca_location = pref_entries.get("caLocation", "")
        cert_location = pref_entries.get("certificateLocation", "")
        location_callsign = pref_entries.get("locationCallsign", "")

        required_pref_keys = ["connectString0", "caLocation", "caPassword", "clientPassword", "certificateLocation"]
        missing_pref_keys = [k for k in required_pref_keys if not pref_entries.get(k)]
        if missing_pref_keys:
            rep.add("FAIL", "required pref keys", "missing or empty keys:\n" + "\n".join(missing_pref_keys))
        else:
            rep.add("PASS", "required pref keys", "all expected soft-cert keys are present")

        if ca_location.startswith("cert/") and cert_location.startswith("cert/"):
            rep.add("PASS", "pref cert locations", f"caLocation={ca_location}\ncertificateLocation={cert_location}")
        else:
            rep.add("WARN", "pref cert locations", f"unexpected values\ncaLocation={ca_location}\ncertificateLocation={cert_location}")

        expected_host = args.expected_host
        if not expected_host and args.zip_url:
            expected_host = urllib.parse.urlparse(args.zip_url).hostname

        if connect_string:
            rep.add("INFO", "connectString0", connect_string)
            m = re.match(r"([^:]+):(\d+):(.+)$", connect_string)
            if m:
                host, port, proto = m.groups()
                if expected_host and host == expected_host:
                    rep.add("PASS", "connectString host", f"host={host} matches expected_host={expected_host}")
                elif expected_host:
                    rep.add("WARN", "connectString host", f"host={host} expected_host={expected_host}")
                else:
                    rep.add("INFO", "connectString parsed", f"host={host}\nport={port}\nproto={proto}")
            else:
                rep.add("WARN", "connectString parsed", f"unexpected format: {connect_string}")

        if args.expected_callsign:
            if location_callsign == args.expected_callsign:
                rep.add("PASS", "locationCallsign", f"{location_callsign} matches expected")
            else:
                rep.add("WARN", "locationCallsign", f"pref has {location_callsign!r}, expected {args.expected_callsign!r}")
        elif location_callsign:
            rep.add("INFO", "locationCallsign", location_callsign)

        if openssl_available():
            client_open = test_pkcs12_password(client_p12, client_password, use_legacy=False)
            if client_open.returncode == 0:
                rep.add("PASS", "clientCert password", "clientCert.p12 opens with password from config.pref")
            else:
                rep.add("FAIL", "clientCert password", client_open.stderr or client_open.stdout or "openssl pkcs12 failed")

            ca_open_normal = test_pkcs12_password(ca_p12, ca_password, use_legacy=False)
            if ca_open_normal.returncode == 0:
                rep.add("PASS", "caCert password", "caCert.p12 opens normally with password from config.pref")
                ca_legacy = False
            else:
                ca_open_legacy = test_pkcs12_password(ca_p12, ca_password, use_legacy=True)
                if ca_open_legacy.returncode == 0:
                    rep.add(
                        "WARN",
                        "caCert password",
                        "caCert.p12 opens only with openssl -legacy; password is correct but PKCS#12 format is legacy/older",
                    )
                    ca_legacy = True
                else:
                    rep.add("FAIL", "caCert password", ca_open_normal.stderr or ca_open_legacy.stderr or "openssl pkcs12 failed")
                    ca_legacy = False

            ca_pem = temp_root / "ca.pem"
            client_pem = temp_root / "client.pem"
            ca_extract = extract_pkcs12_cert(ca_p12, ca_pem, ca_password, use_legacy=ca_legacy, kind="ca")
            client_extract = extract_pkcs12_cert(client_p12, client_pem, client_password, use_legacy=False, kind="client")

            if ca_extract.returncode == 0 and ca_pem.exists():
                rep.add("PASS", "extract CA cert", str(ca_pem))
            else:
                rep.add("FAIL", "extract CA cert", ca_extract.stderr or ca_extract.stdout or "failed")
            if client_extract.returncode == 0 and client_pem.exists():
                rep.add("PASS", "extract client cert", str(client_pem))
            else:
                rep.add("FAIL", "extract client cert", client_extract.stderr or client_extract.stdout or "failed")

            if ca_pem.exists() and client_pem.exists():
                ca_subject, ca_issuer = x509_subject_issuer(ca_pem)
                client_subject, client_issuer = x509_subject_issuer(client_pem)
                rep.add("INFO", "CA cert", f"subject={ca_subject}\nissuer={ca_issuer}\nsha256={x509_fingerprint(ca_pem)}")
                rep.add("INFO", "client cert", f"subject={client_subject}\nissuer={client_issuer}\nsha256={x509_fingerprint(client_pem)}")

                if ca_subject == ca_issuer:
                    rep.add("PASS", "CA self-signed", "CA subject matches issuer")
                else:
                    rep.add("WARN", "CA self-signed", "CA subject does not match issuer; package CA may be intermediate or unexpected")

                if client_issuer == ca_subject:
                    rep.add("PASS", "client issuer", "client issuer matches package CA subject")
                else:
                    rep.add("WARN", "client issuer", f"client issuer does not exactly match package CA subject\nclient issuer={client_issuer}\nca subject={ca_subject}")

                verify_normal = verify_chain(ca_pem, client_pem, sslclient=False)
                if verify_normal.returncode == 0:
                    rep.add("PASS", "verify chain", verify_normal.stdout.strip())
                else:
                    rep.add("FAIL", "verify chain", verify_normal.stderr or verify_normal.stdout or "openssl verify failed")

                verify_sslclient = verify_chain(ca_pem, client_pem, sslclient=True)
                if verify_sslclient.returncode == 0:
                    rep.add("PASS", "verify sslclient", verify_sslclient.stdout.strip())
                else:
                    rep.add("FAIL", "verify sslclient", verify_sslclient.stderr or verify_sslclient.stdout or "openssl verify -purpose sslclient failed")

                cert_dir: Path | None = Path(args.cert_dir) if args.cert_dir else None
                if cert_dir is None:
                    for cand in [Path("/opt/tak/certs/files"), Path("/opt/tak/certs"), Path("/opt/tak")]:
                        if cand.exists() and cand.is_dir():
                            cert_dir = cand
                            break
                if cert_dir is not None:
                    compare_against_local_cert_dir(rep, cert_dir, ca_p12, client_p12, ca_pem)
        else:
            rep.add("WARN", "openssl", "openssl not found; skipping PKCS#12 and chain verification")

        userauth_path: Path | None
        if args.userauth:
            userauth_path = Path(args.userauth)
        else:
            userauth_path = autodetect_file([
                Path("/opt/tak/UserAuthenticationFile.xml"),
                Path("/opt/tak/certs/files/UserAuthenticationFile.xml"),
                Path("/opt/tak/certs/UserAuthenticationFile.xml"),
            ])

        if userauth_path and userauth_path.name == "UserAuthenticationFile.xml" and userauth_path.exists():
            rep.add("INFO", "UserAuthenticationFile.xml", str(userauth_path))
            try:
                root = ET.parse(userauth_path).getroot()
                rep.add("PASS", "UserAuthenticationFile.xml parse", "XML parsed successfully")
                needles: list[tuple[str, str]] = []
                if args.expected_user:
                    needles.append(("expected-user", args.expected_user))
                if args.expected_callsign:
                    needles.append(("expected-callsign", args.expected_callsign))
                if location_callsign and not args.expected_callsign:
                    needles.append(("pref-locationCallsign", location_callsign))
                cn = None
                # Try to pull CN from already-added INFO result if certs were extracted.
                # Cleaner: extract directly from client cert PEM if it exists.
                client_pem = temp_root / "client.pem"
                if client_pem.exists():
                    client_subject, _ = x509_subject_issuer(client_pem)
                    cn = extract_cn(client_subject)
                if cn:
                    needles.append(("client-cert-cn", cn))

                if not needles:
                    rep.add("INFO", "UserAuthenticationFile.xml search", "no expected-user/callsign available; not searching")
                else:
                    for label, needle in needles:
                        hits = iter_xml_hits(root, needle)
                        if hits:
                            rep.add("PASS", f"UserAuthenticationFile.xml search {label}", f"needle={needle!r}\nhits:\n" + "\n".join(hits[:20]))
                        else:
                            rep.add("WARN", f"UserAuthenticationFile.xml search {label}", f"needle={needle!r}\nno hits found")
            except Exception as e:  # noqa: BLE001
                rep.add("FAIL", "UserAuthenticationFile.xml", f"failed to parse/search: {e}")
        else:
            if args.userauth:
                rep.add("WARN", "UserAuthenticationFile.xml", f"not found: {args.userauth}")
            else:
                rep.add("INFO", "UserAuthenticationFile.xml", "not found in common default locations")

        print(rep.render_json() if args.json else rep.render_text())
        if args.keep_temp:
            print(f"\nTEMP_DIR={temp_root}")
        return 1 if rep.has_failures() else 0
    finally:
        if args.keep_temp:
            try:
                temp_ctx._finalizer.detach()  # type: ignore[attr-defined]
            except Exception:
                pass
        else:
            temp_ctx.cleanup()


if __name__ == "__main__":
    sys.exit(main())
