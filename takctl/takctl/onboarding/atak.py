from __future__ import annotations

import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request

from takctl.onboarding.http import bool_q, forwarded_host_only, password_from_req, q, qi
from takctl.onboarding.policy import Policy, PolicyError


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# -----------------------------------------------------------------------------
# URL builders
# -----------------------------------------------------------------------------

def atak_package_url(base: str, username: str) -> str:
    return f"{base}/api/onboarding/users/{username}/packages/atak/package.zip?regen=1"


def atak_package_creds_url(base: str, username: str) -> str:
    return f"{base}/api/onboarding/users/{username}/packages/atak/package-creds/package.zip?regen=1"


def qr_payload(client: str, package_url: str, host: str) -> str:
    """
    Client-specific QR payloads.

    - ATAK: tak:// import intent import?url=<urlencoded https package url>
    - iTAK: Quick Connect line
    - WinTAK: plain https URL
    """
    c = (client or "").strip().lower()
    if c == "atak":
        return "tak://com.atakmap.app/import?url=" + quote(package_url, safe="")
    if c == "itak":
        return f"TAK Server,{host},8089,ssl"
    return package_url


# -----------------------------------------------------------------------------
# Path A/C enroll payloads (experimental)
# -----------------------------------------------------------------------------

def atak_enroll_payload(req: Request) -> str:
    host = q(req, "enroll_host", None) or forwarded_host_only(req)
    port = qi(req, "enroll_port")
    use_ssl = bool_q(req, "enroll_ssl", True)

    # Passwordless enroll deeplink: points ATAK at enrollment endpoint.
    # User enters username/password manually in ATAK UI.
    qs: list[tuple[str, str]] = [("host", host)]
    if port is not None:
        qs.append(("port", str(port)))
    qs.append(("ssl", "true" if use_ssl else "false"))
    qstr = "&".join(f"{k}={quote(v, safe='')}" for k, v in qs)
    return "tak://com.atakmap.app/enroll?" + qstr


def atak_enroll_creds_payload(req: Request, username: str) -> str:
    host = q(req, "enroll_host", None) or forwarded_host_only(req)
    port = qi(req, "enroll_port")
    use_ssl = bool_q(req, "enroll_ssl", True)

    pw = password_from_req(req)
    if not pw:
        raise HTTPException(status_code=400, detail="password required (x-taks-password header or ?password=...)")

    qs: list[tuple[str, str]] = [
        ("host", host),
        ("username", username),
        ("password", pw),
        ("ssl", "true" if use_ssl else "false"),
    ]
    if port is not None:
        qs.insert(1, ("port", str(port)))

    qstr = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in qs)
    return "tak://com.atakmap.app/enroll?" + qstr


# -----------------------------------------------------------------------------
# ATAK package writer
# -----------------------------------------------------------------------------

def write_atak_package_zip(out_zip: Path, username: str, req: Request, include_creds: bool, base: str) -> None:
    """
    Minimal ATAK mission package:
      - MANIFEST/manifest.xml
      - certs/config.pref
      - meta.json

    Option C experiment:
      When include_creds=True, inject (cot_streams):
        useAuth0=true
        cacheCreds0="Cache credentials"
        username0=<username>
        password0=<password>

    IMPORTANT:
      - ATAK will download the zip without custom headers, so for QR-driven
        package-creds flow we rely on ?password=... (or another mechanism) to
        reach this function.
      - This is an experiment: it may or may not actually seed ATAK's auth DB.
    """
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    host = q(req, "host", None) or forwarded_host_only(req)
    port = qi(req, "port") or 8089
    use_ssl = bool_q(req, "ssl", True)
    connect = f"{host}:{port}" + (":ssl" if use_ssl else "")

    policy_id = q(req, "policy_id", None) or "hemvarnet"
    ctx = {
        "unit": q(req, "unit", "") or "",
        "n": q(req, "n", "") or "",
        "role": q(req, "role", "member") or "member",
        "company": qi(req, "company"),
        "platoon": qi(req, "platoon"),
        "battalion_role": q(req, "battalion_role", "") or "",
    }

    try:
        pol = Policy(policy_id)
        ident = pol.resolve_identity(ctx)
        policy_meta = pol.meta()
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    uid = str(uuid.uuid4())

    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<MissionPackageManifest version="2">\n'
        "  <Configuration>\n"
        '    <Parameter name="name" value="TAKS Onboarding"/>\n'
        f'    <Parameter name="uid" value="{uid}"/>\n'
        '    <Parameter name="onReceiveImport" value="true"/>\n'
        "  </Configuration>\n"
        "  <Contents>\n"
        '    <Content ignore="false" zipEntry="certs/config.pref"/>\n'
        "  </Contents>\n"
        "</MissionPackageManifest>\n"
    )

    role_entry = ""
    if getattr(ident, "atak_role_type", None):
        role_entry = f'    <entry key="atakRoleType" class="class java.lang.String">{ident.atak_role_type}</entry>\n'

    auth_entries = ""
    pw_used = False
    if include_creds:
        pw = password_from_req(req)
        if not pw:
            raise HTTPException(status_code=400, detail="password required for package-creds (x-taks-password header or ?password=...)")

        # Option C injection into cot_streams. Keep it boring and explicit.
        # (These keys are NOT stripped by ImportPrefResolver per your source inspection.)
        auth_entries = (
            '    <entry key="useAuth0" class="class java.lang.Boolean">true</entry>\n'
            '    <entry key="cacheCreds0" class="class java.lang.String">Cache credentials</entry>\n'
            f'    <entry key="username0" class="class java.lang.String">{username}</entry>\n'
            f'    <entry key="password0" class="class java.lang.String">{pw}</entry>\n'
        )
        pw_used = True

    config_pref = (
        "<?xml version='1.0' encoding='ASCII' standalone='yes'?>\n"
        "<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        '    <entry key="count" class="class java.lang.Integer">1</entry>\n'
        '    <entry key="description0" class="class java.lang.String">TAK Server</entry>\n'
        '    <entry key="enabled0" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="connectString0" class="class java.lang.String">{connect}</entry>\n'
        f"{auth_entries}"
        "  </preference>\n"
        "\n"
        '  <preference version="1" name="com.atakmap.app_preferences">\n'
        '    <entry key="displayServerConnectionWidget" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="locationCallsign" class="class java.lang.String">{ident.callsign}</entry>\n'
        f'    <entry key="locationTeam" class="class java.lang.String">{ident.team}</entry>\n'
        f"{role_entry}"
        "  </preference>\n"
        "</preferences>\n"
    )

    meta = {
        "username": username,
        "generated_at_utc": now_utc_iso(),
        "takctl_base": base,
        "policy": {"id": policy_id, **policy_meta},
        "ctx": ctx,
        "identity": {"callsign": ident.callsign, "team": ident.team, "atak_role_type": getattr(ident, "atak_role_type", None)},
        "server_connect": {"host": host, "port": port, "ssl": bool(use_ssl), "connectString0": connect},
        "package_mode": "package-creds" if include_creds else "package",
        "option_c": {"embedded_creds": bool(include_creds), "password_present": bool(pw_used)},
        "note": "ATAK import package: server connect + callsign/team. Optionally embeds enrollment creds (experiment).",
    }

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest_xml)
        z.writestr("certs/config.pref", config_pref)
        z.writestr("meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
