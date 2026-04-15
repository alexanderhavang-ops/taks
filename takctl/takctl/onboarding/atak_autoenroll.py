from __future__ import annotations

import json
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


def _trust_material(out_zip: Path) -> tuple[Path, str, str, str, str]:
    ca_name = "caCert.p12"
    ca_zip_rel = f"certs/{ca_name}"
    ca_cfg_rel = f"cert/{ca_name}"

    ca_path, ca_password = _atak.resolve_truststore_material(
        extra_candidates=[out_zip.parent / ca_name, out_zip.parent / "truststore-root.p12"]
    )
    return ca_path, ca_password, ca_name, ca_zip_rel, ca_cfg_rel


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
        '    <entry key="cacheCreds0" class="class java.lang.Boolean">true</entry>\n'
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
        ca_path, ca_password, ca_name, ca_zip_rel, ca_cfg_rel = _trust_material(out_zip)

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
