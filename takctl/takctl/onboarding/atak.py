from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request

from takctl.onboarding.http import bool_q, forwarded_host_only, password_from_req, q, qi
from takctl.onboarding.policy import Policy, PolicyError
from takctl.config import load_config, load_secrets
from takctl.onboarding.selection import load_selection


_TRUTHY = ("1", "true", "yes", "y", "on")


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in _TRUTHY


def _read_runtime_ca_password() -> str:
    try:
        sec = load_secrets()
        return str(sec.get("cert_capass", "") or "").strip()
    except Exception:
        return ""


def _read_runtime_user_cert_password() -> str:
    envp = Path("/opt/tak/certs/tak-cert-identity.env")
    try:
        raw = envp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    vals: dict[str, str] = {}
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

    return (vals.get("PASS") or "").strip()


def _read_cert_generation_password() -> str:
    try:
        sec = load_secrets()
    except Exception:
        return ""

    return str(sec.get("cert_pass", "") or "").strip()


def _read_known_identity_password(username: str) -> str:
    u = str(username or "").strip()
    if not u:
        return ""

    try:
        from takctl.onboarding.service_builder import build_service
        svc = build_service()
        ident = svc.store.get_identity(u)
    except Exception:
        return ""

    if ident is None:
        return ""

    if bool(getattr(ident, "password_known", False)):
        pw = str(getattr(ident, "password", "") or "").strip()
        if pw:
            return pw

    return ""


def _service_identity_export_password(username: str) -> str:
    u = str(username or "").strip()
    if not u:
        return ""

    try:
        cfg = load_config()
    except Exception:
        cfg = {}

    specials = {
        str(cfg.get("martine_username", "martine") or "martine").strip(),
        str(cfg.get("takctl_admin_user", "admin") or "admin").strip(),
    }

    if u in specials:
        return _read_runtime_user_cert_password()

    return ""


def _read_user_key_unlock_password(username: str) -> str:
    u = str(username or "").strip()
    if not u:
        return ""

    pw = _service_identity_export_password(u)
    if pw:
        return pw

    pw = _read_cert_generation_password()
    if pw:
        return pw

    return ""


def _read_user_client_password(username: str) -> str:
    u = str(username or "").strip()
    if not u:
        return ""

    pw = _read_known_identity_password(u)
    if pw:
        return pw

    pw = _service_identity_export_password(u)
    if pw:
        return pw

    return ""


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cfg_bool_with_fallback(cfg, primary: str, legacy: str, default: bool = False) -> bool:
    for key in (primary, legacy):
        try:
            raw = str(cfg.get(key, "") or "").strip().lower()
        except Exception:
            raw = ""
        if raw:
            return raw in _TRUTHY
    return default


def package_password_policy(cfg=None) -> dict[str, bool]:
    if cfg is None:
        cfg = load_config()
    return {
        "include_client_password": _cfg_bool_with_fallback(
            cfg,
            "soft_cert_include_client_password",
            "include_client_password_in_package",
            default=False,
        ),
        "include_truststore_password": _cfg_bool_with_fallback(
            cfg,
            "soft_cert_include_truststore_password",
            "include_truststore_password_in_package",
            default=False,
        ),
    }


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

    user_key_pass = _read_user_key_unlock_password(username)
    if not user_key_pass:
        raise HTTPException(status_code=400, detail="missing key unlock password for user cert export")

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
        raise HTTPException(
            status_code=500,
            detail=f"openssl pkcs12 export failed for {username}: {(p.stdout or '').strip()}",
        )

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
    c = (client or "").strip().lower()
    if c == "atak":
        return "tak://com.atakmap.app/import?url=" + quote(package_url, safe="")
    if c == "itak":
        p = 8446 if port is None else int(port)
        ssl_mode = "ssl" if (True if use_ssl is None else bool(use_ssl)) else "tcp"
        return f"TAK Server,{host},{p},{ssl_mode}"
    return package_url


def atak_enroll_payload_values(
    *,
    host: str,
    port: int | None = None,
    use_ssl: bool = True,
    username: str | None = None,
    password: str | None = None,
) -> str:
    qs: list[tuple[str, str]] = [("host", host)]
    if port is not None:
        qs.append(("port", str(port)))
    if username is not None and str(username).strip():
        qs.append(("username", str(username)))
    if password is not None and str(password).strip():
        qs.append(("token", str(password)))
    qs.append(("ssl", "true" if use_ssl else "false"))
    qstr = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in qs)
    return "tak://com.atakmap.app/enroll?" + qstr


def atak_enroll_payload(req: Request) -> str:
    host = q(req, "enroll_host", None) or forwarded_host_only(req)
    port = qi(req, "enroll_port")
    use_ssl = bool_q(req, "enroll_ssl", True)
    return atak_enroll_payload_values(host=host, port=port, use_ssl=use_ssl)


def atak_enroll_creds_payload(req: Request, username: str) -> str:
    host = q(req, "enroll_host", None) or forwarded_host_only(req)
    port = qi(req, "enroll_port")
    use_ssl = bool_q(req, "enroll_ssl", True)

    pw = password_from_req(req)
    if not pw:
        raise HTTPException(status_code=400, detail="password required (x-taks-password header or ?password=...)")

    return atak_enroll_payload_values(
        host=host,
        port=port,
        use_ssl=use_ssl,
        username=username,
        password=pw,
    )


def resolve_identity_bundle(username: str, req: Request) -> dict[str, Any]:
    sel = load_selection(username) or {}
    if not isinstance(sel, dict):
        sel = {}

    sel_ctx = dict((sel.get("ctx") or {}))
    ep = dict((sel.get("endpoints") or {}))

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
        use_ssl = _truthy(str(ep.get("stream_ssl") or "true"))

    connect = f"{host}:{port}" + (":ssl" if use_ssl else "")

    from takctl.onboarding.policy_registry import default_policy_id
    default_pid = default_policy_id()
    policy_id = q(req, "policy_id", None) or sel_ctx.get("policy_id") or default_pid
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

    role_value = normalize_atak_role_type(getattr(ident, "atak_role_type", None)) or "Team Member"

    return {
        "selection": sel,
        "selection_ctx": sel_ctx,
        "endpoints": ep,
        "host": host,
        "port": port,
        "ssl": bool(use_ssl),
        "connect": connect,
        "policy_id": policy_id,
        "policy_meta": policy_meta,
        "ctx": ctx,
        "identity": ident,
        "role_value": role_value,
    }


def resolve_truststore_material(extra_candidates: list[Path] | None = None) -> tuple[Path, str]:
    ca_candidates = [
        Path("/opt/tak/certs/files/01_TRUST/truststore-root.p12"),
        Path("/opt/tak/certs/files") / "caCert.p12",
        Path("/opt/tak/certs") / "caCert.p12",
    ]
    for p in list(extra_candidates or []):
        ca_candidates.append(p)

    ca_path = None
    for cand in ca_candidates:
        if cand.exists() and cand.is_file():
            ca_path = cand
            break
    if ca_path is None:
        raise HTTPException(status_code=400, detail="missing caCert/truststore p12")

    ca_password = _read_runtime_ca_password()
    if not ca_password:
        raise HTTPException(status_code=400, detail="missing CA password")

    return ca_path, ca_password
