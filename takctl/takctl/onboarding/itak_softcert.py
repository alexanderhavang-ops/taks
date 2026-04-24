from __future__ import annotations
from takctl.onboarding.password_policy import sanitize_pref_xml

import json
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, Request

from takctl.config import load_config
from takctl.onboarding.http import q
from takctl.onboarding import atak as _atak


def write_itak_soft_cert_zip(
    out_zip: Path,
    username: str,
    req: Request,
    base: str,
) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    bundle = _atak.resolve_identity_bundle(username, req)
    ident = bundle["identity"]
    role_value = bundle["role_value"]
    ep = bundle["endpoints"]

    ca_name = "caCert.p12"
    ca_zip_rel = f"certs/{ca_name}"
    ca_cfg_rel = f"cert/{ca_name}"
    ca_path, ca_password = _atak.resolve_truststore_material(
        extra_candidates=[out_zip.parent / ca_name, out_zip.parent / "truststore-root.p12"]
    )

    cfg = load_config()
    policy = _atak.package_password_policy(cfg)
    include_client_pw = bool(policy["include_client_password"])
    include_trust_pw = bool(policy["include_truststore_password"])

    client_name = "clientCert.p12"
    client_zip_rel = f"certs/{client_name}"
    client_cfg_rel = f"cert/{client_name}"

    client_password = (
        q(req, "client_password", None)
        or str(ep.get("client_password") or "").strip()
        or _atak._read_user_client_password(username)
    )
    if not client_password:
        raise HTTPException(status_code=400, detail="missing client password for iTAK soft-cert package")

    client_tmp = out_zip.parent / f"{username}.itak.client.tmp.p12"
    export_info = _atak._export_user_client_p12(
        username=username,
        out_p12=client_tmp,
        client_password=client_password,
    )
    client_p12_bytes = client_tmp.read_bytes()
    try:
        client_tmp.unlink()
    except Exception:
        pass

    ca_pw_entry = (
        f'    <entry key="caPassword" class="class java.lang.String">{ca_password}</entry>\n'
        if include_trust_pw else ""
    )
    client_pw_entry = (
        f'    <entry key="clientPassword" class="class java.lang.String">{client_password}</entry>\n'
        if include_client_pw else ""
    )

    config_pref = (
        "<?xml version='1.0' encoding='ASCII' standalone='yes'?>\n"
        "<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        '    <entry key="count" class="class java.lang.Integer">1</entry>\n'
        f'    <entry key="description0" class="class java.lang.String">{username} @ {bundle["host"]}</entry>\n'
        '    <entry key="enabled0" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="connectString0" class="class java.lang.String">{bundle["connect"]}</entry>\n'
        "  </preference>\n"
        '  <preference version="1" name="com.atakmap.app_preferences">\n'
        '    <entry key="displayServerConnectionWidget" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="caLocation" class="class java.lang.String">{ca_cfg_rel}</entry>\n'
        f"{ca_pw_entry}"
        f"{client_pw_entry}"
        f'    <entry key="certificateLocation" class="class java.lang.String">{client_cfg_rel}</entry>\n'
        f'    <entry key="locationCallsign" class="class java.lang.String">{ident.callsign}</entry>\n'
        f'    <entry key="locationTeam" class="class java.lang.String">{ident.team}</entry>\n'
        f'    <entry key="atakRoleType" class="class java.lang.String">{role_value}</entry>\n'
        "  </preference>\n"
        "</preferences>\n"
    )

    manifest_xml = (
        '<MissionPackageManifest version="2">\n'
        "  <Configuration>\n"
        f'    <Parameter name="uid" value="{uuid.uuid4()}"/>\n'
        '    <Parameter name="name" value="TAK_Server.zip"/>\n'
        '    <Parameter name="onReceiveDelete" value="true"/>\n'
        "  </Configuration>\n"
        "  <Contents>\n"
        '    <Content ignore="false" zipEntry="certs/config.pref"/>\n'
        f'    <Content ignore="false" zipEntry="{ca_zip_rel}"/>\n'
        f'    <Content ignore="false" zipEntry="{client_zip_rel}"/>\n'
        "  </Contents>\n"
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
        },
        "ca_cert": {
            "source_path": str(ca_path),
            "zip_rel": ca_zip_rel,
            "config_rel": ca_cfg_rel,
            "zip_root_name": ca_name,
            "password_present": bool(ca_password),
            "password_embedded": bool(include_trust_pw),
        },
        "client_cert": {
            "export": export_info,
            "zip_rel": client_zip_rel,
            "config_rel": client_cfg_rel,
            "zip_root_name": client_name,
            "password_present": bool(client_password),
            "password_embedded": bool(include_client_pw),
            "user_cert_evidence": _atak._user_cert_evidence(username),
        },
        "package_mode": "itak-soft-cert",
        "note": "iTAK soft-certificate mission package.",
    }

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest_xml)
        z.writestr("certs/config.pref", sanitize_pref_xml(config_pref))
        z.writestr(ca_zip_rel, ca_path.read_bytes())
        z.writestr(client_zip_rel, client_p12_bytes)
        z.writestr("meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
