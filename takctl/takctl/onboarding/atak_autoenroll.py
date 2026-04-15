from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, Request

from takctl.config import load_config
from takctl.onboarding.http import password_from_req
from takctl.onboarding import atak as _atak


_TRUTHY = ("1", "true", "yes", "y", "on")


def _cfg_bool(cfg, *keys: str, default: bool = False) -> bool:
    for key in keys:
        try:
            raw = str(cfg.get(key, "") or "").strip().lower()
        except Exception:
            raw = ""
        if raw:
            return raw in _TRUTHY
    return default


def _auto_enroll_policy(cfg=None) -> dict[str, bool]:
    if cfg is None:
        cfg = load_config()
    return {
        "include_truststore": _cfg_bool(
            cfg,
            "atak_auto_enroll_include_truststore",
            "auto_enroll_include_truststore",
            default=True,
        ),
        "include_truststore_password": _cfg_bool(
            cfg,
            "soft_cert_include_truststore_password",
            "include_truststore_password_in_package",
            default=False,
        ),
    }


def _run_checked(cmd: list[str], *, input_text: str | None = None, timeout: int = 30) -> str:
    p = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stdout or "").strip() or f"command failed: {' '.join(cmd)}")
    return p.stdout or ""


def _pem_cert_blocks(text: str) -> list[str]:
    out: list[str] = []
    begin = "-----BEGIN CERTIFICATE-----"
    end = "-----END CERTIFICATE-----"
    pos = 0
    while True:
        s = text.find(begin, pos)
        if s < 0:
            break
        e = text.find(end, s)
        if e < 0:
            break
        e += len(end)
        block = text[s:e]
        if not block.endswith("\n"):
            block += "\n"
        out.append(block)
        pos = e
    return out


def _fetch_tls_chain_pems(host: str, port: int = 8446) -> list[str]:
    out = _run_checked(
        [
            "openssl", "s_client",
            "-connect", f"{host}:{port}",
            "-servername", host,
            "-showcerts",
        ],
        input_text="",
        timeout=20,
    )
    certs = _pem_cert_blocks(out)
    if not certs:
        raise RuntimeError(f"no certificates received from {host}:{port}")
    return certs


def _x509_subject_issuer(cert_path: Path) -> tuple[str, str]:
    subj = _run_checked(["openssl", "x509", "-in", str(cert_path), "-noout", "-subject"]).strip()
    issuer = _run_checked(["openssl", "x509", "-in", str(cert_path), "-noout", "-issuer"]).strip()
    subj = subj.split("subject=", 1)[-1].strip()
    issuer = issuer.split("issuer=", 1)[-1].strip()
    return subj, issuer


def _find_system_cert_by_subject(subject: str) -> Path | None:
    roots = [Path("/etc/ssl/certs"), Path("/etc/pki/tls/certs")]
    seen: set[str] = set()

    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            sp = str(p.resolve()) if p.exists() else str(p)
            if sp in seen:
                continue
            seen.add(sp)

            if not p.is_file():
                continue

            try:
                out = subprocess.run(
                    ["openssl", "x509", "-in", str(p), "-noout", "-subject"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            except Exception:
                continue

            if out.returncode != 0:
                continue

            got = (out.stdout or "").strip().split("subject=", 1)[-1].strip()
            if got == subject:
                return p

    return None


def _extend_chain_from_system_store(cert_paths: list[Path], tmpdir: Path) -> list[Path]:
    added: list[Path] = []
    current = cert_paths[-1]
    seen_subjects = set()

    for p in cert_paths:
        try:
            subj, _ = _x509_subject_issuer(p)
            seen_subjects.add(subj)
        except Exception:
            pass

    for i in range(4):
        subj, issuer = _x509_subject_issuer(current)
        if subj == issuer:
            break
        if issuer in seen_subjects:
            break

        syscert = _find_system_cert_by_subject(issuer)
        if syscert is None:
            break

        dst = tmpdir / f"system-chain-{i+1}.pem"
        shutil.copy2(syscert, dst)

        added.append(dst)
        seen_subjects.add(issuer)
        current = dst

    return added


def _build_pkcs12_truststore(
    *,
    out_p12: Path,
    store_password: str,
    cert_entries: list[tuple[str, Path]],
) -> None:
    out_p12.parent.mkdir(parents=True, exist_ok=True)
    if out_p12.exists():
        out_p12.unlink()

    _run_checked([
        "keytool",
        "-genkeypair",
        "-alias", "throwaway",
        "-keystore", str(out_p12),
        "-storetype", "PKCS12",
        "-storepass", store_password,
        "-keypass", store_password,
        "-dname", "CN=throwaway",
        "-keyalg", "RSA",
        "-validity", "1",
    ])

    _run_checked([
        "keytool",
        "-delete",
        "-alias", "throwaway",
        "-keystore", str(out_p12),
        "-storetype", "PKCS12",
        "-storepass", store_password,
    ])

    for alias, cert_path in cert_entries:
        _run_checked([
            "keytool",
            "-importcert",
            "-noprompt",
            "-alias", alias,
            "-file", str(cert_path),
            "-keystore", str(out_p12),
            "-storetype", "PKCS12",
            "-storepass", store_password,
        ])


def _trust_material(out_zip: Path, host: str) -> tuple[Path, str, str, str, str]:
    ca_name = "caCert.p12"
    ca_zip_rel = f"certs/{ca_name}"
    ca_cfg_rel = f"cert/{ca_name}"

    ca_password = _atak._read_runtime_ca_password()
    if not ca_password:
        raise HTTPException(status_code=400, detail="missing CA password for ATAK auto-enroll package")

    internal_ca_pem = Path("/opt/tak/certs/files/00_CA/ca.pem")
    if not internal_ca_pem.exists():
        raise HTTPException(status_code=400, detail=f"missing internal CA pem: {internal_ca_pem}")

    try:
        chain_pems = _fetch_tls_chain_pems(host, 8446)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to fetch 8446 TLS chain: {e}")

    tmpdir = Path(tempfile.mkdtemp(prefix="atak-autoenroll-ca-", dir=str(out_zip.parent)))
    cert_entries: list[tuple[str, Path]] = []

    internal_copy = tmpdir / "tak-internal-ca.pem"
    shutil.copy2(internal_ca_pem, internal_copy)
    cert_entries.append(("tak-internal-ca", internal_copy))

    chain_paths: list[Path] = []
    for idx, pem in enumerate(chain_pems[1:], start=1):
        p = tmpdir / f"ext-chain-{idx}.pem"
        p.write_text(pem, encoding="utf-8")
        chain_paths.append(p)
        cert_entries.append((f"ext-chain-{idx}", p))

    if chain_paths:
        for idx, p in enumerate(_extend_chain_from_system_store(chain_paths, tmpdir), start=1):
            cert_entries.append((f"system-chain-{idx}", p))

    hybrid_p12 = out_zip.parent / f"{out_zip.stem}.hybrid.caCert.p12"
    try:
        _build_pkcs12_truststore(
            out_p12=hybrid_p12,
            store_password=ca_password,
            cert_entries=cert_entries,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to build hybrid truststore: {e}")

    return hybrid_p12, ca_password, ca_name, ca_zip_rel, ca_cfg_rel


def _auto_enroll_config_pref(
    *,
    username: str,
    host: str,
    connect: str,
    ident,
    role_value: str,
    include_truststore: bool,
    include_trust_pw: bool,
    ca_cfg_rel: str,
    ca_password: str,
    include_creds: bool,
    enroll_password: str,
) -> str:
    trust_flag = "true" if include_truststore else "false"

    username_entry = (
        f'    <entry key="username0" class="class java.lang.String">{username}</entry>\n'
        if include_creds and username
        else ""
    )
    password_entry = (
        f'    <entry key="password0" class="class java.lang.String">{enroll_password}</entry>\n'
        if include_creds and enroll_password
        else ""
    )
    ca_location0_entry = (
        f'    <entry key="caLocation0" class="class java.lang.String">{ca_cfg_rel}</entry>\n'
        if include_truststore
        else ""
    )
    ca_password0_entry = (
        f'    <entry key="caPassword0" class="class java.lang.String">{ca_password}</entry>\n'
        if include_truststore and include_trust_pw
        else ""
    )

    return (
        "<?xml version='1.0' encoding='ASCII' standalone='yes'?>\n"
        "<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        '    <entry key="count" class="class java.lang.Integer">1</entry>\n'
        f'    <entry key="description0" class="class java.lang.String">{username} @ {host}</entry>\n'
        '    <entry key="enabled0" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="connectString0" class="class java.lang.String">{connect}</entry>\n'
        '    <entry key="useAuth0" class="class java.lang.Boolean">true</entry>\n'
        '    <entry key="cacheCreds0" class="class java.lang.String">Cache credentials</entry>\n'
        f'    <entry key="enrollForCertificateWithTrust0" class="class java.lang.Boolean">{trust_flag}</entry>\n'
        f"{username_entry}"
        f"{password_entry}"
        f"{ca_location0_entry}"
        f"{ca_password0_entry}"
        "  </preference>\n"
        '  <preference version="1" name="com.atakmap.app_preferences">\n'
        '    <entry key="displayServerConnectionWidget" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="locationCallsign" class="class java.lang.String">{ident.callsign}</entry>\n'
        f'    <entry key="locationTeam" class="class java.lang.String">{ident.team}</entry>\n'
        f'    <entry key="atakRoleType" class="class java.lang.String">{role_value}</entry>\n'
        "  </preference>\n"
        "</preferences>\n"
    )


def write_atak_auto_enroll_package_zip(
    out_zip: Path,
    username: str,
    req: Request,
    include_creds: bool,
    base: str,
) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    bundle = _atak.resolve_identity_bundle(username, req)
    ident = bundle["identity"]
    role_value = bundle["role_value"]

    cfg = load_config()
    policy = _auto_enroll_policy(cfg)
    include_truststore = bool(policy["include_truststore"])
    include_trust_pw = bool(policy["include_truststore_password"])

    enroll_password = ""
    if include_creds:
        enroll_password = password_from_req(req)
        if not enroll_password:
            raise HTTPException(
                status_code=400,
                detail="password required for ATAK auto-enroll creds package",
            )

    ca_path = None
    ca_password = ""
    ca_name = ""
    ca_zip_rel = ""
    ca_cfg_rel = ""
    if include_truststore:
        ca_path, ca_password, ca_name, ca_zip_rel, ca_cfg_rel = _trust_material(out_zip, bundle["host"])

    config_pref = _auto_enroll_config_pref(
        username=username,
        host=bundle["host"],
        connect=bundle["connect"],
        ident=ident,
        role_value=role_value,
        include_truststore=include_truststore,
        include_trust_pw=include_trust_pw,
        ca_cfg_rel=ca_cfg_rel,
        ca_password=ca_password,
        include_creds=include_creds,
        enroll_password=enroll_password,
    )

    manifest_contents = ['    <Content ignore="false" zipEntry="certs/config.pref"/>\n']
    if include_truststore:
        manifest_contents.append(f'    <Content ignore="false" zipEntry="{ca_zip_rel}"/>\n')

    manifest_xml = (
        '<MissionPackageManifest version="2">\n'
        "  <Configuration>\n"
        f'    <Parameter name="uid" value="{uuid.uuid4()}"/>\n'
        '    <Parameter name="name" value="TAK_Server.zip"/>\n'
        '    <Parameter name="onReceiveDelete" value="true"/>\n'
        "  </Configuration>\n"
        "  <Contents>\n"
        + "".join(manifest_contents)
        + "  </Contents>\n"
        "</MissionPackageManifest>\n"
    )

    meta = {
        "username": username,
        "generated_at_utc": _atak.now_utc_iso(),
        "takctl_base": base,
        "policy": {"id": bundle["policy_id"], **bundle["policy_meta"]},
        "selection_ctx": bundle["selection_ctx"],
        "ctx": bundle["ctx"],
        "identity": {
            "callsign": ident.callsign,
            "team": ident.team,
            "atak_role_type": role_value,
            "atak_role_type_raw": getattr(ident, "atak_role_type", None),
            "callsign_policy_effective": getattr(ident, "callsign_policy_effective", None),
            "callsign_variants": getattr(ident, "callsign_variants", None),
        },
        "server_connect": {
            "host": bundle["host"],
            "port": bundle["port"],
            "ssl": bool(bundle["ssl"]),
            "connectString0": bundle["connect"],
            "username": username,
        },
        "auto_enroll": {
            "enrollForCertificateWithTrust0": bool(include_truststore),
            "truststore_included": bool(include_truststore),
            "truststore_password_embedded": bool(include_truststore and include_trust_pw),
            "credentials_embedded": bool(include_creds),
        },
        "ca_cert": {
            "source_path": str(ca_path) if ca_path else "",
            "zip_rel": ca_zip_rel,
            "config_rel": ca_cfg_rel,
            "zip_root_name": ca_name,
            "password_present": bool(ca_password) if include_truststore else False,
            "password_embedded": bool(include_truststore and include_trust_pw),
        },
        "client_cert": {
            "present": False,
        },
        "package_mode": "atak-auto-enroll-creds" if include_creds else "atak-auto-enroll",
        "note": "ATAK auto-enroll package. Never includes client certificate.",
    }

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest_xml)
        z.writestr("certs/config.pref", config_pref)
        if include_truststore and ca_path is not None:
            z.writestr(ca_zip_rel, ca_path.read_bytes())
        z.writestr("meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")


def write_atak_auto_enroll_zip(
    out_zip: Path,
    username: str,
    req: Request,
    base: str,
    include_creds: bool = False,
) -> None:
    write_atak_auto_enroll_package_zip(
        out_zip=out_zip,
        username=username,
        req=req,
        include_creds=include_creds,
        base=base,
    )
