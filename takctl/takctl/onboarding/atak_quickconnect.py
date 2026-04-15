from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException, Request

from takctl.onboarding.http import bool_q, forwarded_host_only, password_from_req, q, qi


def qr_payload(package_url: str, host: str, port: int | None = None, use_ssl: bool | None = None) -> str:
    del host, port, use_ssl
    return "tak://com.atakmap.app/import?url=" + quote(package_url, safe="")


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
