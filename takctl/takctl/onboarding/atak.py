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
from takctl.config import load_config
from takctl.onboarding.selection import load_selection


def _read_runtime_ca_password() -> str:
    envp = Path("/opt/tak/certs/tak-cert-identity.env")
    try:
        raw = envp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    vals = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or not line.startswith("export "):
            continue
        body = line[len("export "):]
        if "=" not in body:
            continue
        k, v = body.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        vals[k] = v

    return (vals.get("CAPASS") or vals.get("PASS") or "").strip()


def _read_runtime_user_cert_password() -> str:
    envp = Path("/opt/tak/certs/tak-cert-identity.env")
    try:
        raw = envp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    vals = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or not line.startswith("export "):
            continue
        body = line[len("export "):]
        if "=" not in body:
            continue
        k, v = body.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        vals[k] = v

    return (vals.get("PASS") or vals.get("CAPASS") or "").strip()


def _read_user_client_password(username: str) -> str:
    u = (username or "").strip()
    if u:
        for pwf in (
            Path("/opt/tak/certs/files/04_USERS") / u / ".client-password",
            Path("/opt/tak/takctl-state/onboarding/identities") / f"{u}.client-password",
        ):
            try:
                v = pwf.read_text(encoding="utf-8", errors="replace").strip()
                if v:
                    return v
            except Exception:
                pass
    return _read_runtime_user_cert_password()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _user_cert_dir(username: str) -> Path:
    return Path("/opt/tak/certs/files/04_USERS") / username

def _user_cert_paths(username: str) -> dict[str, Path]:
    d = _user_cert_dir(username)
    return {
        "dir": d,
        "key": d / f"{username}.key",
        "pem": d / f"{username}.pem",
        "p12": d / f"{username}.p12",
        "modern_p12": d / f"{username}.modern.p12",
        "jks": d / f"{username}.jks",
    }

def _user_cert_evidence(username: str) -> dict[str, str | bool]:
    paths = _user_cert_paths(username)
    return {
        "dir": str(paths["dir"]),
        "key_exists": paths["key"].exists(),
        "pem_exists": paths["pem"].exists(),
        "p12_exists": paths["p12"].exists(),
        "modern_p12_exists": paths["modern_p12"].exists(),
        "jks_exists": paths["jks"].exists(),
    }


def _export_user_client_p12(
    *,
    username: str,
    out_p12: Path,
    client_password: str,
) -> dict[str, str]:
    import subprocess

    paths = _user_cert_paths(username)
    key_path = paths["key"]
    pem_path = paths["pem"]
    ca_pem = Path("/opt/tak/certs/files/00_CA/ca.pem")

    if not key_path.exists():
        raise HTTPException(status_code=400, detail=f"missing user key for {username}: {key_path}")
    if not pem_path.exists():
        raise HTTPException(status_code=400, detail=f"missing user cert for {username}: {pem_path}")
    if not ca_pem.exists():
        raise HTTPException(status_code=400, detail=f"missing CA pem: {ca_pem}")

    user_key_pass = _read_user_client_password(username)
    if not user_key_pass:
        raise HTTPException(status_code=400, detail="missing user_key_pass / PASS for user cert export")

    out_p12.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "openssl", "pkcs12", "-export",
        "-inkey", str(key_path),
        "-passin", f"pass:{user_key_pass}",
        "-in", str(pem_path),
        "-certfile", str(ca_pem),
        "-out", str(out_p12),
        "-passout", f"pass:{client_password}",
    ]

    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=f"openssl pkcs12 export failed for {username}: {(p.stdout or '').strip()}")

    return {
        "out_p12": str(out_p12),
        "key_path": str(key_path),
        "pem_path": str(pem_path),
        "ca_pem": str(ca_pem),
    }



def normalize_atak_role_type(v: str | None) -> str | None:
    raw = (v or "").strip()
    if not raw:
        return None

    allowed = {
        "Team Member",
        "Team Lead",
        "HQ",
        "Sniper",
        "Medic",
        "Forward Observer",
        "RTO",
        "K9",
    }
    if raw in allowed:
        return raw

    key = raw.lower()
    mapping = {
        "soldier": "Team Member",
        "member": "Team Member",
        "operator": "Team Member",
        "commander": "Team Lead",
        "leader": "Team Lead",
        "team leader": "Team Lead",
        "hq": "HQ",
        "headquarters": "HQ",
        "sniper": "Sniper",
        "medic": "Medic",
        "forward observer": "Forward Observer",
        "fo": "Forward Observer",
        "rto": "RTO",
        "radio operator": "RTO",
        "signalist": "RTO",
        "k9": "K9",
        "dog": "K9",
        "handler": "K9",
    }
    return mapping.get(key, "Team Member")


# -----------------------------------------------------------------------------
# URL builders
# -----------------------------------------------------------------------------

def atak_package_url(base: str, username: str) -> str:
    return f"{base}/api/onboarding/users/{username}/packages/atak/package.zip?regen=1"


def atak_package_creds_url(base: str, username: str) -> str:
    return f"{base}/api/onboarding/users/{username}/packages/atak/package-creds/package.zip?regen=1"


def itak_package_url(base: str, username: str) -> str:
    return f"{base}/api/onboarding/users/{username}/packages/itak/package.zip?regen=1"


def qr_payload(
    client: str,
    package_url: str,
    host: str,
    port: int | None = None,
    use_ssl: bool | None = None,
) -> str:
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
        return package_url
    return package_url


# -----------------------------------------------------------------------------
# Path A/C enroll payloads (experimental)
# -----------------------------------------------------------------------------

def atak_enroll_payload(req: Request) -> str:
    host = q(req, "enroll_host", None) or forwarded_host_only(req)
    port = qi(req, "enroll_port")
    use_ssl = bool_q(req, "enroll_ssl", True)

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
# ATAK / iTAK package writer
# -----------------------------------------------------------------------------



def write_atak_cert_package_zip(out_zip: Path, username: str, req: Request, include_creds: bool, base: str) -> None:
    """
    ATAK soft-certificate mission package, aligned to known-good template:

      - MANIFEST/manifest.xml
      - certs/config.pref
      - certs/caCert.p12
      - certs/clientCert.p12
      - meta.json
    """
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    sel = load_selection(username) or {}
    sel_ctx = dict((sel.get("ctx") or {}))
    ep = dict((sel.get("endpoints") or {})) if isinstance(sel, dict) else {}

    host = (
        q(req, "host", None)
        or ep.get("stream_host")
        or forwarded_host_only(req)
    )

    try:
        port = qi(req, "port")
    except Exception:
        port = None
    if port is None:
        try:
            port = int(str(ep.get("stream_port") or "").strip() or "8089")
        except Exception:
            port = 8089

    ssl_q = req.query_params.get("ssl")
    if ssl_q is not None and str(ssl_q).strip():
        use_ssl = bool_q(req, "ssl", True)
    else:
        use_ssl = str(ep.get("stream_ssl") or "true").strip().lower() in ("1", "true", "yes", "y", "on")

    connect = f"{host}:{port}" + (":ssl" if use_ssl else "")

    policy_id = q(req, "policy_id", None) or sel_ctx.get("policy_id") or "hemvarnet"
    ctx = dict(sel_ctx)

    overrides = {
        "policy_id": q(req, "policy_id", None),
        "unit": q(req, "unit", None),
        "n": q(req, "n", None),
        "role": q(req, "role", None),
        "company": q(req, "company", None),
        "platoon": q(req, "platoon", None),
        "group": q(req, "group", None),
        "battalion": q(req, "battalion", None),
        "battalion_fal": q(req, "battalion_fal", None),
        "battalion_role": q(req, "battalion_role", None),
        "callsign": q(req, "callsign", None),
        "callsign_policy": q(req, "callsign_policy", None),
        "team": q(req, "team", None),
        "atak_role_type": q(req, "atak_role_type", None),
        "remarks": q(req, "remarks", None),
        "email": q(req, "email", None),
    }
    for k, v in overrides.items():
        if v is not None and str(v).strip():
            ctx[k] = v

    ctx.setdefault("unit", "")
    ctx.setdefault("n", "")
    ctx.setdefault("role", "member")
    ctx.setdefault("company", "")
    ctx.setdefault("platoon", "")
    ctx.setdefault("group", "")
    ctx.setdefault("battalion", "")
    ctx.setdefault("battalion_fal", "")
    ctx.setdefault("battalion_role", "")

    try:
        pol = Policy(policy_id)
        ident = pol.resolve_identity(ctx)
        policy_meta = pol.meta()
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    uid = str(uuid.uuid4())

    ca_name = "caCert.p12"
    ca_zip_rel = f"certs/{ca_name}"
    ca_cfg_rel = f"cert/{ca_name}"

    ca_candidates = [
        Path("/opt/tak/certs/files/01_TRUST/truststore-root.p12"),
        Path("/opt/tak/certs/files") / "caCert.p12",
        Path("/opt/tak/certs") / "caCert.p12",
        out_zip.parent / ca_name,
        out_zip.parent / "truststore-root.p12",
    ]
    ca_path = None
    for cand in ca_candidates:
        if cand.exists() and cand.is_file():
            ca_path = cand
            break
    if ca_path is None:
        raise HTTPException(status_code=400, detail="missing caCert/truststore p12 for ATAK cert package")

    ca_password = (
        q(req, "ca_password", None)
        or str(ep.get("ca_password") or "").strip()
        or _read_runtime_ca_password()
    )
    if not ca_password:
        raise HTTPException(status_code=400, detail="missing CA password for ATAK cert package")

    cfg = load_config()
    include_client_pw = str(cfg.get("include_client_password_in_package", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    include_trust_pw = str(cfg.get("include_truststore_password_in_package", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    client_name = "clientCert.p12"
    client_zip_rel = f"certs/{client_name}"
    client_cfg_rel = f"cert/{client_name}"

    client_password = (
        q(req, "client_password", None)
        or str(ep.get("client_password") or "").strip()
        or _read_user_client_password(username)
    )
    if not client_password:
        raise HTTPException(status_code=400, detail="missing client password for ATAK cert package")

    client_tmp = out_zip.parent / f"{username}.atak.client.tmp.p12"
    export_info = _export_user_client_p12(
        username=username,
        out_p12=client_tmp,
        client_password=client_password,
    )
    client_p12_bytes = client_tmp.read_bytes()
    try:
        client_tmp.unlink()
    except Exception:
        pass

    role_value = normalize_atak_role_type(getattr(ident, "atak_role_type", None)) or "Team Member"

    ca_pw_entry = f'    <entry key="caPassword" class="class java.lang.String">{ca_password}</entry>\n' if include_trust_pw else ""
    client_pw_entry = f'    <entry key="clientPassword" class="class java.lang.String">{client_password}</entry>\n' if include_client_pw else ""

    config_pref = (
        "<?xml version='1.0' encoding='ASCII' standalone='yes'?>\n"
        "<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        '    <entry key="count" class="class java.lang.Integer">1</entry>\n'
        f'    <entry key="description0" class="class java.lang.String">{username} @ {host}</entry>\n'
        '    <entry key="enabled0" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="connectString0" class="class java.lang.String">{connect}</entry>\n'
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
        f'    <Parameter name="uid" value="{uid}"/>\n'
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
        "generated_at_utc": now_utc_iso(),
        "takctl_base": base,
        "policy": {"id": policy_id, **policy_meta},
        "selection_ctx": sel_ctx,
        "ctx": ctx,
        "identity": {
            "callsign": ident.callsign,
            "team": ident.team,
            "atak_role_type": role_value,
            "atak_role_type_raw": getattr(ident, "atak_role_type", None),
            "callsign_policy_effective": getattr(ident, "callsign_policy_effective", None),
            "callsign_variants": getattr(ident, "callsign_variants", None),
        },
        "server_connect": {
            "host": host,
            "port": port,
            "ssl": bool(use_ssl),
            "connectString0": connect,
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
        },
        "package_mode": "atak-cert-package-creds" if include_creds else "atak-cert-package",
        "option_c": {"embedded_creds": bool(include_creds), "password_present": bool(include_creds)},
        "note": "ATAK soft-certificate mission package.",
    }

    ca_bytes = ca_path.read_bytes()

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest_xml)
        z.writestr("certs/config.pref", config_pref)
        z.writestr(ca_zip_rel, ca_bytes)
        z.writestr(client_zip_rel, client_p12_bytes)
        z.writestr("meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")

def write_atak_auto_enroll_package_zip(out_zip: Path, username: str, req: Request, include_creds: bool, base: str) -> None:
    raise HTTPException(status_code=501, detail="ATAK auto-enroll package writer not split out yet")


def write_atak_package_zip(out_zip: Path, username: str, req: Request, include_creds: bool, base: str) -> None:
    cfg = load_config()
    raw_mode = str(cfg.get("onboarding_mode", "") or "").strip().lower()
    if raw_mode not in ("auto-enroll", "cert-creation"):
        legacy = str(cfg.get("create_cert_with_user", "") or "").strip().lower()
        raw_mode = "cert-creation" if legacy in ("1", "true", "yes", "y", "on") else "auto-enroll"

    if raw_mode == "auto-enroll":
        return write_atak_auto_enroll_package_zip(
            out_zip=out_zip,
            username=username,
            req=req,
            include_creds=include_creds,
            base=base,
        )

    return write_atak_cert_package_zip(
        out_zip=out_zip,
        username=username,
        req=req,
        include_creds=include_creds,
        base=base,
    )




def write_itak_package_zip(out_zip: Path, username: str, req: Request, base: str) -> None:
    """
    iTAK package, but intentionally shaped like the currently working ATAK
    soft-cert mission package format:

      - MANIFEST/manifest.xml
      - certs/config.pref
      - certs/caCert.p12
      - certs/clientCert.p12
      - meta.json
    """
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    sel = load_selection(username) or {}
    sel_ctx = dict((sel.get("ctx") or {}))
    ep = dict((sel.get("endpoints") or {})) if isinstance(sel, dict) else {}

    host = (
        q(req, "host", None)
        or str(ep.get("stream_host") or "").strip()
        or forwarded_host_only(req)
    )
    try:
        port = qi(req, "port")
    except Exception:
        port = None
    if port is None:
        try:
            port = int(str(ep.get("stream_port") or "").strip() or "8089")
        except Exception:
            port = 8089

    ssl_q = req.query_params.get("ssl")
    if ssl_q is not None and str(ssl_q).strip():
        use_ssl = bool_q(req, "ssl", True)
    else:
        use_ssl = str(ep.get("stream_ssl") or "true").strip().lower() in ("1", "true", "yes", "y", "on")

    connect = f"{host}:{port}" + (":ssl" if use_ssl else "")

    policy_id = q(req, "policy_id", None) or sel_ctx.get("policy_id") or "hemvarnet"
    ctx = dict(sel_ctx)

    overrides = {
        "policy_id": q(req, "policy_id", None),
        "unit": q(req, "unit", None),
        "n": q(req, "n", None),
        "role": q(req, "role", None),
        "company": q(req, "company", None),
        "platoon": q(req, "platoon", None),
        "group": q(req, "group", None),
        "battalion": q(req, "battalion", None),
        "battalion_fal": q(req, "battalion_fal", None),
        "battalion_role": q(req, "battalion_role", None),
        "callsign": q(req, "callsign", None),
        "callsign_policy": q(req, "callsign_policy", None),
        "team": q(req, "team", None),
        "atak_role_type": q(req, "atak_role_type", None),
        "remarks": q(req, "remarks", None),
        "email": q(req, "email", None),
    }
    for k, v in overrides.items():
        if v is not None and str(v).strip():
            ctx[k] = v

    ctx.setdefault("unit", "")
    ctx.setdefault("n", "")
    ctx.setdefault("role", "member")
    ctx.setdefault("company", "")
    ctx.setdefault("platoon", "")
    ctx.setdefault("group", "")
    ctx.setdefault("battalion", "")
    ctx.setdefault("battalion_fal", "")
    ctx.setdefault("battalion_role", "")

    try:
        pol = Policy(policy_id)
        ident = pol.resolve_identity(ctx)
        policy_meta = pol.meta()
    except PolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    uid = str(uuid.uuid4())

    ca_name = "caCert.p12"
    ca_zip_rel = f"certs/{ca_name}"
    ca_cfg_rel = f"cert/{ca_name}"

    ca_candidates = [
        Path("/opt/tak/certs/files/01_TRUST/truststore-root.p12"),
        Path("/opt/tak/certs/files") / "caCert.p12",
        Path("/opt/tak/certs") / "caCert.p12",
    ]
    ca_path = None
    for cand in ca_candidates:
        if cand.exists() and cand.is_file():
            ca_path = cand
            break
    if ca_path is None:
        raise HTTPException(status_code=400, detail="missing caCert/truststore p12 for iTAK package")

    ca_password = (
        q(req, "ca_password", None)
        or str(ep.get("ca_password") or "").strip()
        or _read_runtime_ca_password()
    )
    if not ca_password:
        raise HTTPException(status_code=400, detail="missing CA password for iTAK package")

    cfg = load_config()
    include_client_pw = str(cfg.get("include_client_password_in_package", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
    include_trust_pw = str(cfg.get("include_truststore_password_in_package", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")

    client_name = "clientCert.p12"
    client_zip_rel = f"certs/{client_name}"
    client_cfg_rel = f"cert/{client_name}"

    client_password = (
        q(req, "client_password", None)
        or str(ep.get("client_password") or "").strip()
        or _read_user_client_password(username)
    )
    if not client_password:
        raise HTTPException(status_code=400, detail="missing client password for iTAK package")

    client_tmp = out_zip.parent / f"{username}.itak.client.tmp.p12"
    export_info = _export_user_client_p12(
        username=username,
        out_p12=client_tmp,
        client_password=client_password,
    )
    client_p12_bytes = client_tmp.read_bytes()
    try:
        client_tmp.unlink()
    except Exception:
        pass

    role_value = normalize_atak_role_type(getattr(ident, "atak_role_type", None)) or "Team Member"

    ca_pw_entry = f'    <entry key="caPassword" class="class java.lang.String">{ca_password}</entry>\n' if include_trust_pw else ""
    client_pw_entry = f'    <entry key="clientPassword" class="class java.lang.String">{client_password}</entry>\n' if include_client_pw else ""

    config_pref = (
        "<?xml version='1.0' encoding='ASCII' standalone='yes'?>\n"
        "<preferences>\n"
        '  <preference version="1" name="cot_streams">\n'
        '    <entry key="count" class="class java.lang.Integer">1</entry>\n'
        f'    <entry key="description0" class="class java.lang.String">{username} @ {host}</entry>\n'
        '    <entry key="enabled0" class="class java.lang.Boolean">true</entry>\n'
        f'    <entry key="connectString0" class="class java.lang.String">{connect}</entry>\n'
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
        f'    <Parameter name="uid" value="{uid}"/>\n'
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
        "generated_at_utc": now_utc_iso(),
        "takctl_base": base,
        "policy": {"id": policy_id, **policy_meta},
        "selection_ctx": sel_ctx,
        "ctx": ctx,
        "identity": {
            "callsign": ident.callsign,
            "team": ident.team,
            "atak_role_type": role_value,
            "atak_role_type_raw": getattr(ident, "atak_role_type", None),
            "callsign_policy_effective": getattr(ident, "callsign_policy_effective", None),
            "callsign_variants": getattr(ident, "callsign_variants", None),
        },
        "server_connect": {
            "host": host,
            "port": port,
            "ssl": bool(use_ssl),
            "connectString0": connect,
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
        },
        "package_mode": "itak-cert-package",
        "note": "iTAK package intentionally shaped like working ATAK soft-cert package.",
    }

    ca_bytes = ca_path.read_bytes()

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST/manifest.xml", manifest_xml)
        z.writestr("certs/config.pref", config_pref)
        z.writestr(ca_zip_rel, ca_bytes)
        z.writestr(client_zip_rel, client_p12_bytes)
        z.writestr("meta.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
