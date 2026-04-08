from __future__ import annotations

import http.client
import os
import re
import secrets
import socket
import ssl
from pathlib import Path
from typing import Optional
from urllib.parse import quote


def _read_bytes(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def _multipart_form_data(
    *,
    field_name: str,
    filename: str,
    content_type: str,
    payload: bytes,
) -> tuple[bytes, str]:
    boundary = "----martine-" + secrets.token_hex(16)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        f"\r\n"
    ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, boundary


def _https_connection(
    *,
    host: str,
    port: int,
    cert_pem: str | Path,
    key_pem: str | Path,
    ca_pem: str | Path | None = None,
    verify_server: bool = False,
    timeout: float = 20.0,
) -> http.client.HTTPSConnection:
    if verify_server:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if ca_pem:
            ctx.load_verify_locations(cafile=str(ca_pem))
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl._create_unverified_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    ctx.load_cert_chain(certfile=str(cert_pem), keyfile=str(key_pem))
    return http.client.HTTPSConnection(host=host, port=port, context=ctx, timeout=timeout)


def upload_mission_package(
    *,
    host: str,
    port: int = 8443,
    cert_pem: str | Path,
    key_pem: str | Path,
    zip_path: str | Path,
    ca_pem: str | Path | None = None,
    verify_server: bool = False,
    timeout: float = 20.0,
) -> dict:
    zip_path = Path(zip_path)
    payload = _read_bytes(zip_path)
    body, boundary = _multipart_form_data(
        field_name="assetfile",
        filename=zip_path.name,
        content_type="application/zip",
        payload=payload,
    )

    path = f"/Marti/sync/missionupload?filename={quote(zip_path.name)}"
    conn = _https_connection(
        host=host,
        port=port,
        cert_pem=cert_pem,
        key_pem=key_pem,
        ca_pem=ca_pem,
        verify_server=verify_server,
        timeout=timeout,
    )
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "Accept": "*/*",
            },
        )
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()

    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"missionupload failed: HTTP {resp.status}: {resp_body[:500]}")

    m = re.search(r"hash=([0-9a-f]+)", resp_body, flags=re.IGNORECASE)
    if not m:
        raise RuntimeError(f"could not parse missionupload hash from response: {resp_body[:500]}")

    return {
        "ok": True,
        "status": resp.status,
        "body": resp_body,
        "hash": m.group(1),
    }


def send_cot_tls(
    *,
    host: str,
    port: int = 8089,
    cert_pem: str | Path,
    key_pem: str | Path,
    ca_pem: str | Path,
    xml_text: str,
    server_hostname: Optional[str] = None,
    timeout: float = 10.0,
) -> dict:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(ca_pem))
    ctx.load_cert_chain(certfile=str(cert_pem), keyfile=str(key_pem))

    with socket.create_connection((host, port), timeout=timeout) as raw:
        with ctx.wrap_socket(raw, server_hostname=(server_hostname or host)) as tls_sock:
            tls_sock.settimeout(timeout)
            tls_sock.sendall(xml_text.encode("utf-8"))

    return {
        "ok": True,
        "host": host,
        "port": port,
    }
