from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


MAX_ZIP_BYTES = 75 * 1024 * 1024
XML_PARSE_MAX_BYTES = 3 * 1024 * 1024


@dataclasses.dataclass
class CheckResult:
    status: str
    group: str
    name: str
    detail: str


class Reporter:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def add(self, status: str, group: str, name: str, detail: str = "") -> None:
        status = str(status or "INFO").upper()
        if status not in {"PASS", "WARN", "FAIL", "INFO"}:
            status = "INFO"
        self.results.append(
            CheckResult(
                status=status,
                group=str(group or "general"),
                name=str(name or "check"),
                detail=str(detail or "").rstrip(),
            )
        )

    def has_failures(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0, "INFO": 0}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def as_list(self) -> list[dict[str, str]]:
        return [dataclasses.asdict(r) for r in self.results]


def _mask_secret_value(key: str, value: Any) -> Any:
    k = str(key or "").lower()
    if any(x in k for x in ("pass", "password", "secret", "token", "key")):
        v = str(value or "")
        if not v:
            return ""
        return "********"
    return value


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def openssl_available() -> bool:
    return shutil.which("openssl") is not None


def load_zip_from_url(url: str, dst: Path, *, timeout_sec: int = 25, max_bytes: int = MAX_ZIP_BYTES) -> tuple[int, str]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("zip_url must use http or https")
    if not parsed.netloc:
        raise ValueError("zip_url is missing host")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "takctl-package-check/1.0",
            "Accept": "application/zip, application/octet-stream, */*",
        },
        method="GET",
    )

    total = 0
    content_type = ""
    with urllib.request.urlopen(req, timeout=timeout_sec) as r:  # nosec - admin supplied diagnostic URL
        content_type = str(r.headers.get("content-type") or "")
        cl = r.headers.get("content-length")
        if cl:
            try:
                if int(cl) > max_bytes:
                    raise ValueError(f"download too large: content-length={cl}, max={max_bytes}")
            except ValueError:
                if str(cl).isdigit():
                    raise

        with dst.open("wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"download too large: exceeded {max_bytes} bytes")
                f.write(chunk)

    return total, content_type


def detect_manifest_name(names: list[str]) -> str | None:
    candidates = [
        "MANIFEST/manifest.xml",
        "manifest.xml",
        "MANIFEST.xml",
    ]
    lower_map = {n.lower(): n for n in names}
    for c in candidates:
        hit = lower_map.get(c.lower())
        if hit:
            return hit
    for n in names:
        if n.lower().endswith("manifest.xml"):
            return n
    return None


def _is_bad_zip_name(name: str) -> bool:
    raw = str(name or "")
    if not raw:
        return True
    if raw.startswith(("/", "\\")):
        return True
    if re.match(r"^[A-Za-z]:", raw):
        return True
    parts = raw.replace("\\", "/").split("/")
    return any(p in ("..", ".") for p in parts)


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
            out[key] = value
            if pref_name:
                out[f"{pref_name}:{key}"] = value
    return out


def _sanitized_pref_entries(pref_entries: dict[str, str]) -> dict[str, str]:
    return {
        k: _mask_secret_value(k, v)
        for k, v in sorted(pref_entries.items())
        if ":" not in k
    }


def _read_zip_text(zf: zipfile.ZipFile, name: str, *, limit: int = XML_PARSE_MAX_BYTES) -> str:
    info = zf.getinfo(name)
    if info.file_size > limit:
        raise ValueError(f"{name} is too large to parse safely: {info.file_size} bytes")
    return zf.read(name).decode("utf-8", errors="replace")


def _manifest_params(root: ET.Element) -> dict[str, str]:
    return {
        str(p.attrib.get("name", "")): str(p.attrib.get("value", ""))
        for p in root.findall("./Configuration/Parameter")
        if p.attrib.get("name")
    }


def _manifest_entries(root: ET.Element) -> list[str]:
    entries: list[str] = []
    for c in root.findall("./Contents/Content"):
        z = str(c.attrib.get("zipEntry", "") or "").strip()
        if z:
            entries.append(z)
    return entries


def _find_pref_name(names: list[str]) -> str | None:
    preferred = [
        "certs/config.pref",
        "cert/config.pref",
        "config.pref",
    ]
    lower_map = {n.lower(): n for n in names}
    for p in preferred:
        if p.lower() in lower_map:
            return lower_map[p.lower()]
    for n in names:
        if n.lower().endswith(".pref"):
            return n
    return None


def _find_entries(names: list[str], suffix: str) -> list[str]:
    want = suffix.lower().strip("/")
    return [n for n in names if n.lower().replace("\\", "/").endswith(want)]


def _first_entry(names: list[str], suffixes: list[str]) -> str | None:
    for suffix in suffixes:
        hits = _find_entries(names, suffix)
        if hits:
            return hits[0]
    return None


def _detect_platform_style(names: list[str], pref_entries: dict[str, str], xml_text_by_name: dict[str, str]) -> tuple[str, list[str]]:
    evidence: list[str] = []
    lower_names = [n.lower() for n in names]
    keys = {k.lower() for k in pref_entries.keys() if ":" not in k}

    if any(n.endswith(".mobileconfig") or n.endswith(".plist") for n in lower_names):
        evidence.append("mobileconfig/plist file present")
        return "itak-ios-style", evidence

    if any("itak" in n for n in lower_names):
        evidence.append("path/name contains itak")
        return "itak-ios-style", evidence

    if "connectstring0" in keys or "locationcallsign" in keys:
        evidence.append("ATAK-style config.pref keys present")
    if any(n.endswith("config.pref") for n in lower_names):
        evidence.append("config.pref present")
    if any("/certs/" in n or n.startswith("certs/") or "/cert/" in n or n.startswith("cert/") for n in lower_names):
        evidence.append("cert/certs directory layout present")
    if evidence:
        return "atak-android-style", evidence

    joined = "\n".join(xml_text_by_name.values()).lower()
    if "itak" in joined or "ios" in joined:
        evidence.append("XML text mentions itak/ios")
        return "itak-ios-style", evidence

    return "unknown", ["no strong platform-style markers found"]


def _detect_package_type(names: list[str], pref_entries: dict[str, str], manifest_params: dict[str, str]) -> tuple[str, list[str]]:
    evidence: list[str] = []
    lower_names = [n.lower().replace("\\", "/") for n in names]
    keys = {k.lower() for k in pref_entries.keys() if ":" not in k}
    param_blob = json.dumps(manifest_params, ensure_ascii=False).lower()

    has_ca = any(n.endswith("cacert.p12") for n in lower_names)
    has_client = any(n.endswith("clientcert.p12") for n in lower_names)
    has_any_p12 = any(n.endswith(".p12") or n.endswith(".pfx") for n in lower_names)

    if has_ca:
        evidence.append("caCert.p12 present")
    if has_client:
        evidence.append("clientCert.p12 present")
    if "capassword" in keys:
        evidence.append("caPassword present in config.pref")
    if "clientpassword" in keys:
        evidence.append("clientPassword present in config.pref")
    if "certificatelocation" in keys:
        evidence.append("certificateLocation present in config.pref")
    if "calocation" in keys:
        evidence.append("caLocation present in config.pref")

    enroll_markers = sorted(k for k in keys if "enroll" in k or "enrollment" in k)
    if enroll_markers:
        evidence.append("enrollment-related config.pref keys: " + ", ".join(enroll_markers[:12]))
    if "enroll" in param_blob or "enrollment" in param_blob or "auto" in param_blob:
        evidence.append("manifest params mention enroll/auto")

    if has_ca and has_client and {"capassword", "clientpassword"}.issubset(keys):
        return "soft-cert", evidence

    if enroll_markers or ((has_ca or has_any_p12) and not has_client and ("enroll" in param_blob or "enrollment" in param_blob)):
        return "auto-enroll", evidence

    if has_any_p12:
        return "cert-package-unknown", evidence

    return "unknown", evidence or ["no cert/enrollment markers found"]


def _extract_zip_member(zf: zipfile.ZipFile, name: str, dst_dir: Path) -> Path:
    raw = str(name or "").replace("\\", "/")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") or "member"
    dst = dst_dir / safe_name
    dst.write_bytes(zf.read(name))
    return dst


def _try_pkcs12_password(p12_path: Path, password: str, *, legacy: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["openssl", "pkcs12"]
    if legacy:
        cmd.append("-legacy")
    cmd += ["-in", str(p12_path), "-nokeys", "-passin", f"pass:{password}"]
    return run_cmd(cmd)


def _extract_pkcs12_cert(
    p12_path: Path,
    out_pem: Path,
    password: str,
    *,
    legacy: bool,
    cert_kind: str,
) -> subprocess.CompletedProcess[str]:
    cmd = ["openssl", "pkcs12"]
    if legacy:
        cmd.append("-legacy")
    cmd += [
        "-in",
        str(p12_path),
        "-nokeys",
        "-out",
        str(out_pem),
        "-passin",
        f"pass:{password}",
    ]
    if cert_kind == "ca":
        cmd.insert(-4, "-cacerts")
    elif cert_kind == "client":
        cmd.insert(-4, "-clcerts")
    return run_cmd(cmd)


def _x509_info(cert_path: Path) -> dict[str, str]:
    proc = run_cmd(
        [
            "openssl",
            "x509",
            "-in",
            str(cert_path),
            "-noout",
            "-subject",
            "-issuer",
            "-dates",
            "-fingerprint",
            "-sha256",
        ],
        check=True,
    )
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k == "sha256 Fingerprint":
            out["sha256_fingerprint"] = v.replace(":", "").lower()
        else:
            out[k] = v
    return out


def _verify_chain(ca_pem: Path, client_pem: Path, *, sslclient: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["openssl", "verify", "-show_chain"]
    if sslclient:
        cmd += ["-purpose", "sslclient"]
    cmd += ["-CAfile", str(ca_pem), str(client_pem)]
    return run_cmd(cmd)


def _extract_cn(subject: str) -> str | None:
    m = re.search(r"(?:^|,\s*)CN\s*=\s*([^,]+)", str(subject or ""))
    return m.group(1).strip() if m else None


def _common_userauth_path() -> Path | None:
    for p in [
        Path("/opt/tak/UserAuthenticationFile.xml"),
        Path("/opt/tak/certs/files/UserAuthenticationFile.xml"),
        Path("/opt/tak/certs/UserAuthenticationFile.xml"),
    ]:
        if p.exists() and p.is_file():
            return p
    return None


def _iter_xml_hits(root: ET.Element, needle: str) -> list[str]:
    needle_l = str(needle or "").strip().lower()
    if not needle_l:
        return []
    hits: list[str] = []
    for elem in root.iter():
        for k, v in elem.attrib.items():
            if needle_l in str(v).lower():
                hits.append(f"<{elem.tag} {k}={v!r}>")
        txt = (elem.text or "").strip()
        if txt and needle_l in txt.lower():
            hits.append(f"<{elem.tag}> text={txt!r}")
    return hits


def _check_xml_files(rep: Reporter, zf: zipfile.ZipFile, names: list[str]) -> dict[str, str]:
    xml_text_by_name: dict[str, str] = {}
    xml_names = [n for n in names if n.lower().endswith((".xml", ".pref", ".mobileconfig", ".plist"))]
    if not xml_names:
        rep.add("WARN", "xml", "XML/PREF files", "no XML-like files found")
        return xml_text_by_name

    for name in xml_names:
        try:
            txt = _read_zip_text(zf, name)
            ET.fromstring(txt)
            rep.add("PASS", "xml", f"parse {name}", "XML parsed successfully")
            xml_text_by_name[name] = txt
        except Exception as e:
            rep.add("FAIL", "xml", f"parse {name}", str(e))
    return xml_text_by_name


def _check_manifest(rep: Reporter, zf: zipfile.ZipFile, names: list[str]) -> tuple[str | None, dict[str, str], list[str]]:
    manifest_name = detect_manifest_name(names)
    if not manifest_name:
        rep.add("WARN", "manifest", "manifest.xml", "manifest.xml not found; some iTAK/quick-connect packages may not use ATAK data-package manifest layout")
        return None, {}, []

    try:
        manifest_xml = _read_zip_text(zf, manifest_name)
        root = ET.fromstring(manifest_xml)
    except Exception as e:
        rep.add("FAIL", "manifest", "manifest parse", f"{manifest_name}: {e}")
        return manifest_name, {}, []

    version = root.attrib.get("version")
    params = _manifest_params(root)
    entries = _manifest_entries(root)
    missing = [e for e in entries if e and e not in names]

    if version == "2":
        rep.add("PASS", "manifest", "manifest version", "version=2")
    else:
        rep.add("WARN", "manifest", "manifest version", f"expected version=2, got {version!r}")

    rep.add(
        "INFO",
        "manifest",
        "manifest params",
        _safe_json({k: _mask_secret_value(k, v) for k, v in params.items()}),
    )

    if entries and not missing:
        rep.add("PASS", "manifest", "manifest contents", "all manifest zipEntry values exist in the archive")
    elif missing:
        rep.add("FAIL", "manifest", "manifest contents", "missing ZIP entries referenced by manifest:\n" + "\n".join(missing))
    else:
        rep.add("WARN", "manifest", "manifest contents", "manifest has no Contents/Content zipEntry values")

    return manifest_name, params, entries


def _check_pref(rep: Reporter, zf: zipfile.ZipFile, names: list[str]) -> tuple[str | None, dict[str, str]]:
    pref_name = _find_pref_name(names)
    if not pref_name:
        rep.add("WARN", "config", "config.pref", "no .pref file found")
        return None, {}

    try:
        txt = _read_zip_text(zf, pref_name)
        entries = parse_pref_entries(txt)
        rep.add("PASS", "config", "config.pref parse", f"parsed {pref_name}")
        rep.add("INFO", "config", "config.pref keys", _safe_json(_sanitized_pref_entries(entries)))
        return pref_name, entries
    except Exception as e:
        rep.add("FAIL", "config", "config.pref parse", f"{pref_name}: {e}")
        return pref_name, {}


def _check_pref_expected(
    rep: Reporter,
    *,
    pref_entries: dict[str, str],
    zip_url: str,
    expected_host: str | None,
    expected_callsign: str | None,
) -> None:
    if not pref_entries:
        return

    required_soft_keys = ["connectString0", "caLocation", "caPassword", "clientPassword", "certificateLocation"]
    missing_soft = [k for k in required_soft_keys if not pref_entries.get(k)]
    if missing_soft:
        rep.add("INFO", "config", "soft-cert key completeness", "missing or empty soft-cert keys:\n" + "\n".join(missing_soft))
    else:
        rep.add("PASS", "config", "soft-cert key completeness", "all expected soft-cert keys are present")

    connect_string = pref_entries.get("connectString0", "")
    if connect_string:
        rep.add("INFO", "config", "connectString0", connect_string)
        m = re.match(r"([^:]+):(\d+):(.+)$", connect_string)
        host_from_url = urllib.parse.urlparse(zip_url).hostname if zip_url else None
        want_host = expected_host or host_from_url
        if m:
            host, port, proto = m.groups()
            detail = f"host={host}\nport={port}\nproto={proto}"
            if want_host and host == want_host:
                rep.add("PASS", "config", "connectString host", detail + f"\nexpected_host={want_host}")
            elif want_host:
                rep.add("WARN", "config", "connectString host", detail + f"\nexpected_host={want_host}")
            else:
                rep.add("INFO", "config", "connectString parsed", detail)
        else:
            rep.add("WARN", "config", "connectString parsed", f"unexpected format: {connect_string}")

    location_callsign = pref_entries.get("locationCallsign", "")
    if expected_callsign:
        if location_callsign == expected_callsign:
            rep.add("PASS", "config", "locationCallsign", f"{location_callsign} matches expected")
        else:
            rep.add("WARN", "config", "locationCallsign", f"pref has {location_callsign!r}, expected {expected_callsign!r}")
    elif location_callsign:
        rep.add("INFO", "config", "locationCallsign", location_callsign)


def _check_certs(rep: Reporter, zf: zipfile.ZipFile, names: list[str], pref_entries: dict[str, str], temp_root: Path) -> dict[str, Any]:
    cert_summary: dict[str, Any] = {
        "ca_entry": None,
        "client_entry": None,
        "ca_info": None,
        "client_info": None,
        "client_cn": None,
    }

    p12_entries = [n for n in names if n.lower().endswith((".p12", ".pfx"))]
    if not p12_entries:
        rep.add("INFO", "certs", "PKCS#12 files", "no .p12/.pfx files found")
        return cert_summary

    rep.add("INFO", "certs", "PKCS#12 files", "\n".join(p12_entries))

    ca_entry = _first_entry(names, ["certs/caCert.p12", "cert/caCert.p12", "caCert.p12"])
    client_entry = _first_entry(names, ["certs/clientCert.p12", "cert/clientCert.p12", "clientCert.p12"])
    cert_summary["ca_entry"] = ca_entry
    cert_summary["client_entry"] = client_entry

    if not openssl_available():
        rep.add("WARN", "certs", "openssl", "openssl not found; skipping PKCS#12 and x509 verification")
        return cert_summary

    cert_dir = temp_root / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)

    ca_pem: Path | None = None
    client_pem: Path | None = None

    if ca_entry:
        ca_p12 = _extract_zip_member(zf, ca_entry, cert_dir)
        ca_password = pref_entries.get("caPassword", "")
        if not ca_password:
            rep.add("WARN", "certs", "caCert password", "caCert.p12 present but caPassword not found in config.pref")
        else:
            normal = _try_pkcs12_password(ca_p12, ca_password, legacy=False)
            ca_legacy = False
            if normal.returncode == 0:
                rep.add("PASS", "certs", "caCert password", "caCert.p12 opens with caPassword")
            else:
                legacy = _try_pkcs12_password(ca_p12, ca_password, legacy=True)
                if legacy.returncode == 0:
                    ca_legacy = True
                    rep.add("WARN", "certs", "caCert password", "caCert.p12 opens only with openssl -legacy")
                else:
                    rep.add("FAIL", "certs", "caCert password", normal.stderr or legacy.stderr or "openssl pkcs12 failed")

            ca_pem_candidate = temp_root / "ca.pem"
            proc = _extract_pkcs12_cert(ca_p12, ca_pem_candidate, ca_password, legacy=ca_legacy, cert_kind="ca")
            if proc.returncode == 0 and ca_pem_candidate.exists() and ca_pem_candidate.stat().st_size > 0:
                ca_pem = ca_pem_candidate
                rep.add("PASS", "certs", "extract CA cert", "CA certificate extracted")
                try:
                    info = _x509_info(ca_pem)
                    cert_summary["ca_info"] = info
                    rep.add("INFO", "certs", "CA cert", _safe_json(info))
                    if info.get("subject") and info.get("issuer") and info.get("subject") == info.get("issuer"):
                        rep.add("PASS", "certs", "CA self-signed", "CA subject matches issuer")
                    else:
                        rep.add("WARN", "certs", "CA self-signed", "CA subject does not match issuer; package CA may be intermediate or unexpected")
                except Exception as e:
                    rep.add("FAIL", "certs", "CA x509 parse", str(e))
            else:
                rep.add("FAIL", "certs", "extract CA cert", proc.stderr or proc.stdout or "failed")
    else:
        rep.add("INFO", "certs", "caCert.p12", "not found")

    if client_entry:
        client_p12 = _extract_zip_member(zf, client_entry, cert_dir)
        client_password = pref_entries.get("clientPassword", "")
        if not client_password:
            rep.add("WARN", "certs", "clientCert password", "clientCert.p12 present but clientPassword not found in config.pref")
        else:
            proc = _try_pkcs12_password(client_p12, client_password, legacy=False)
            if proc.returncode == 0:
                rep.add("PASS", "certs", "clientCert password", "clientCert.p12 opens with clientPassword")
            else:
                rep.add("FAIL", "certs", "clientCert password", proc.stderr or proc.stdout or "openssl pkcs12 failed")

            client_pem_candidate = temp_root / "client.pem"
            extract = _extract_pkcs12_cert(client_p12, client_pem_candidate, client_password, legacy=False, cert_kind="client")
            if extract.returncode == 0 and client_pem_candidate.exists() and client_pem_candidate.stat().st_size > 0:
                client_pem = client_pem_candidate
                rep.add("PASS", "certs", "extract client cert", "client certificate extracted")
                try:
                    info = _x509_info(client_pem)
                    cert_summary["client_info"] = info
                    cert_summary["client_cn"] = _extract_cn(info.get("subject", ""))
                    rep.add("INFO", "certs", "client cert", _safe_json(info))
                except Exception as e:
                    rep.add("FAIL", "certs", "client x509 parse", str(e))
            else:
                rep.add("FAIL", "certs", "extract client cert", extract.stderr or extract.stdout or "failed")
    else:
        rep.add("INFO", "certs", "clientCert.p12", "not found; this can be expected for auto-enroll packages")

    if ca_pem and client_pem:
        try:
            ca_info = cert_summary.get("ca_info") or {}
            client_info = cert_summary.get("client_info") or {}
            if client_info.get("issuer") == ca_info.get("subject"):
                rep.add("PASS", "certs", "client issuer", "client issuer matches package CA subject")
            else:
                rep.add(
                    "WARN",
                    "certs",
                    "client issuer",
                    f"client issuer={client_info.get('issuer')}\nca subject={ca_info.get('subject')}",
                )

            normal = _verify_chain(ca_pem, client_pem, sslclient=False)
            if normal.returncode == 0:
                rep.add("PASS", "certs", "verify chain", normal.stdout.strip())
            else:
                rep.add("FAIL", "certs", "verify chain", normal.stderr or normal.stdout or "openssl verify failed")

            sslclient = _verify_chain(ca_pem, client_pem, sslclient=True)
            if sslclient.returncode == 0:
                rep.add("PASS", "certs", "verify sslclient", sslclient.stdout.strip())
            else:
                rep.add("FAIL", "certs", "verify sslclient", sslclient.stderr or sslclient.stdout or "openssl verify -purpose sslclient failed")
        except Exception as e:
            rep.add("FAIL", "certs", "verify cert chain", str(e))

    return cert_summary


def _check_userauth(
    rep: Reporter,
    *,
    expected_user: str | None,
    expected_callsign: str | None,
    pref_entries: dict[str, str],
    client_cn: str | None,
) -> None:
    p = _common_userauth_path()
    if not p:
        rep.add("INFO", "local", "UserAuthenticationFile.xml", "not found in common default locations")
        return

    rep.add("INFO", "local", "UserAuthenticationFile.xml", str(p))
    try:
        root = ET.parse(p).getroot()
        rep.add("PASS", "local", "UserAuthenticationFile.xml parse", "XML parsed successfully")
    except Exception as e:
        rep.add("FAIL", "local", "UserAuthenticationFile.xml parse", str(e))
        return

    needles: list[tuple[str, str]] = []
    if expected_user:
        needles.append(("expected-user", expected_user))
    if expected_callsign:
        needles.append(("expected-callsign", expected_callsign))
    elif pref_entries.get("locationCallsign"):
        needles.append(("pref-locationCallsign", pref_entries["locationCallsign"]))
    if client_cn:
        needles.append(("client-cert-cn", client_cn))

    if not needles:
        rep.add("INFO", "local", "UserAuthenticationFile.xml search", "no expected-user/callsign/client CN available; not searching")
        return

    for label, needle in needles:
        hits = _iter_xml_hits(root, needle)
        if hits:
            rep.add("PASS", "local", f"UserAuthenticationFile.xml search {label}", f"needle={needle!r}\nhits:\n" + "\n".join(hits[:20]))
        else:
            rep.add("WARN", "local", f"UserAuthenticationFile.xml search {label}", f"needle={needle!r}\nno hits found")


def check_zip_url(
    zip_url: str,
    *,
    expected_host: str | None = None,
    expected_user: str | None = None,
    expected_callsign: str | None = None,
) -> dict[str, Any]:
    rep = Reporter()

    package_type = "unknown"
    platform_style = "unknown"
    temp_ctx = tempfile.TemporaryDirectory(prefix="takctl-package-check-")
    temp_root = Path(temp_ctx.name)

    try:
        zip_path = temp_root / "package.zip"

        try:
            size, content_type = load_zip_from_url(zip_url, zip_path)
            rep.add(
                "INFO",
                "input",
                "download",
                f"url={zip_url}\nsize={size} bytes\ncontent_type={content_type or '(none)'}\nlocal_copy={zip_path}",
            )
        except Exception as e:
            rep.add("FAIL", "input", "download", str(e))
            return _final_result(rep, package_type=package_type, platform_style=platform_style)

        if not zipfile.is_zipfile(zip_path):
            rep.add("FAIL", "zip", "archive", "input is not a valid ZIP archive")
            return _final_result(rep, package_type=package_type, platform_style=platform_style)

        rep.add(
            "PASS",
            "zip",
            "archive",
            f"valid ZIP archive\nsize={zip_path.stat().st_size} bytes\nsha256={sha256_file(zip_path)}",
        )

        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            names = [i.filename for i in infos]
            rep.add("INFO", "zip", "entries", "\n".join(names) if names else "(empty)")

            bad_names = [n for n in names if _is_bad_zip_name(n)]
            if bad_names:
                rep.add("FAIL", "zip", "entry paths", "unsafe ZIP entry path(s):\n" + "\n".join(bad_names))
            else:
                rep.add("PASS", "zip", "entry paths", "no absolute, parent-directory, or drive-letter paths found")

            encrypted = [i.filename for i in infos if i.flag_bits & 0x1]
            if encrypted:
                rep.add("WARN", "zip", "encryption", "encrypted ZIP entries found:\n" + "\n".join(encrypted))
            else:
                rep.add("PASS", "zip", "encryption", "no encrypted ZIP entries found")

            xml_text_by_name = _check_xml_files(rep, zf, names)
            _manifest_name, manifest_params, _manifest_entries_seen = _check_manifest(rep, zf, names)
            _pref_name, pref_entries = _check_pref(rep, zf, names)

            platform_style, platform_evidence = _detect_platform_style(names, pref_entries, xml_text_by_name)
            rep.add("INFO", "classification", "platform/style", f"{platform_style}\n" + "\n".join(platform_evidence))

            package_type, type_evidence = _detect_package_type(names, pref_entries, manifest_params)
            rep.add("INFO", "classification", "package type", f"{package_type}\n" + "\n".join(type_evidence))

            _check_pref_expected(
                rep,
                pref_entries=pref_entries,
                zip_url=zip_url,
                expected_host=expected_host,
                expected_callsign=expected_callsign,
            )

            cert_summary = _check_certs(rep, zf, names, pref_entries, temp_root)

            _check_userauth(
                rep,
                expected_user=expected_user,
                expected_callsign=expected_callsign,
                pref_entries=pref_entries,
                client_cn=str(cert_summary.get("client_cn") or "") or None,
            )

        return _final_result(rep, package_type=package_type, platform_style=platform_style)
    finally:
        temp_ctx.cleanup()


def _final_result(rep: Reporter, *, package_type: str, platform_style: str) -> dict[str, Any]:
    counts = rep.counts()
    status = "fail" if counts.get("FAIL", 0) else ("warn" if counts.get("WARN", 0) else "pass")
    return {
        "ok": status != "fail",
        "status": status,
        "package_type": package_type,
        "platform_style": platform_style,
        "summary": counts,
        "results": rep.as_list(),
    }
