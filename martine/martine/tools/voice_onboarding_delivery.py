from __future__ import annotations

import http.client
import logging
import socket
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape

from .voice_onboarding_common import (
    DEFAULT_CE,
    DEFAULT_HAE,
    DEFAULT_LAT,
    DEFAULT_LE,
    DEFAULT_LON,
    LOCAL_COT_TLS_PORT,
    LOCAL_MARTI_HTTPS_PORT,
    _iso_z,
    _multipart_body,
    _mtls_context,
    _parse_upload_hash,
    _utc_now,
    _write_text,
)


_LOG = logging.getLogger(__name__)


def _upload_package_https(*, tak_host: str, zip_path: Path, response_path: Path) -> str:
    body_boundary, body = _multipart_body(
        "assetfile",
        zip_path.name,
        zip_path.read_bytes(),
        "application/zip",
    )
    path = f"/Marti/sync/missionupload?filename={quote(zip_path.name)}"
    ctx = _mtls_context()

    conn = http.client.HTTPSConnection(
        host=str(tak_host),
        port=LOCAL_MARTI_HTTPS_PORT,
        context=ctx,
        timeout=30,
    )
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={body_boundary}",
                "Content-Length": str(len(body)),
            },
        )
        resp = conn.getresponse()
        resp_status = int(resp.status)
        resp_text = resp.read().decode("utf-8", errors="replace")
    finally:
        conn.close()

    _write_text(response_path, resp_text)
    if resp_status >= 400:
        raise RuntimeError(f"missionupload failed: HTTP {resp_status}: {resp_text[:500]}")
    return _parse_upload_hash(resp_text)


def _wait_for_uploaded_content(
    *,
    tak_host: str,
    marti_hash: str,
    timeout_seconds: float = 5.0,
    interval_seconds: float = 0.25,
) -> dict[str, Any]:
    path = f"/Marti/sync/content?hash={quote(marti_hash)}"
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    attempts = 0
    last_error = ""

    while True:
        attempts += 1
        ctx = _mtls_context()
        conn = http.client.HTTPSConnection(
            host=str(tak_host),
            port=LOCAL_MARTI_HTTPS_PORT,
            context=ctx,
            timeout=10,
        )
        try:
            conn.request("GET", path, headers={"Accept": "*/*"})
            resp = conn.getresponse()
            body = resp.read()
            if 200 <= int(resp.status) < 300 and body is not None:
                return {
                    "ok": True,
                    "status": int(resp.status),
                    "attempts": attempts,
                    "bytes": len(body),
                    "path": path,
                }
            last_error = f"HTTP {resp.status}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.05, float(interval_seconds)))

    raise RuntimeError(
        f"uploaded content not readable yet after {attempts} attempts for hash {marti_hash}: {last_error}"
    )


def _build_fileshare_xml(
    *,
    dest_callsign: str,
    dest_uid: str = "",
    sender_uid: str,
    sender_callsign: str,
    display_name: str,
    display_filename: str,
    sender_url: str,
    package_size: int,
    package_hash: str,
    stale_hours: int = 2,
) -> tuple[str, str]:
    event_uid = str(uuid.uuid4()).lower()
    ack_uid = str(uuid.uuid4()).lower()
    now = _utc_now()
    time_now = _iso_z(now)
    time_stale = _iso_z(now + timedelta(hours=max(1, int(stale_hours or 2))))

    dest_attrs: list[str] = []
    if str(dest_uid or "").strip():
        dest_attrs.append(f'uid="{escape(str(dest_uid).strip())}"')
    if str(dest_callsign or "").strip():
        dest_attrs.append(f'callsign="{escape(str(dest_callsign).strip())}"')
    dest_xml = f"    <marti><dest {' '.join(dest_attrs)}/></marti>\n" if dest_attrs else ""

    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        f"<event version='2.0' uid='{escape(event_uid)}' type='b-f-t-r' time='{time_now}' start='{time_now}' stale='{time_stale}' how='h-e'>\n"
        f"  <point lat='{DEFAULT_LAT}' lon='{DEFAULT_LON}' hae='{DEFAULT_HAE}' ce='{DEFAULT_CE}' le='{DEFAULT_LE}' />\n"
        "  <detail>\n"
        f"    <fileshare filename=\"{escape(display_filename)}\" senderUrl=\"{escape(sender_url)}\" sizeInBytes=\"{int(package_size)}\" sha256=\"{escape(package_hash)}\" senderUid=\"{escape(sender_uid)}\" senderCallsign=\"{escape(sender_callsign)}\" name=\"{escape(display_name)}\"/>\n"
        f"    <ackrequest uid=\"{escape(ack_uid)}\" ackrequested=\"true\" tag=\"{escape(display_name)}\"/>\n"
        f"{dest_xml}"
        "  </detail>\n"
        "</event>\n"
    )
    return event_uid, xml


def _send_cot_tls(*, xml_text: str, host: str, port: int = LOCAL_COT_TLS_PORT) -> None:
    ctx = _mtls_context()
    payload = xml_text.encode("utf-8")

    with socket.create_connection((host, int(port)), timeout=15) as raw:
        with ctx.wrap_socket(raw, server_hostname=str(host)) as sock:
            _LOG.info(
                "voice_onboarding cot_tls_connected host=%s port=%s tls=%s cipher=%s",
                host,
                port,
                sock.version(),
                sock.cipher(),
            )

            pre_recv_len = 0
            try:
                sock.settimeout(0.35)
                pre = sock.recv(4096)
                pre_recv_len = len(pre or b"")
            except socket.timeout:
                pre_recv_len = 0
            except Exception as e:
                _LOG.info(
                    "voice_onboarding cot_tls_pre_recv_error host=%s port=%s err=%s",
                    host,
                    port,
                    f"{type(e).__name__}: {e}",
                )
            finally:
                try:
                    sock.settimeout(15)
                except Exception:
                    pass

            _LOG.info(
                "voice_onboarding cot_tls_pre_send host=%s port=%s pre_recv_len=%s payload_len=%s",
                host,
                port,
                pre_recv_len,
                len(payload),
            )

            time.sleep(0.20)
            sock.sendall(payload)
            _LOG.info(
                "voice_onboarding cot_tls_sent host=%s port=%s payload_len=%s",
                host,
                port,
                len(payload),
            )

            time.sleep(0.50)

            post_recv_len = 0
            try:
                sock.settimeout(0.35)
                post = sock.recv(4096)
                post_recv_len = len(post or b"")
            except socket.timeout:
                post_recv_len = 0
            except Exception as e:
                _LOG.info(
                    "voice_onboarding cot_tls_post_recv_error host=%s port=%s err=%s",
                    host,
                    port,
                    f"{type(e).__name__}: {e}",
                )
            finally:
                try:
                    sock.settimeout(15)
                except Exception:
                    pass

            _LOG.info(
                "voice_onboarding cot_tls_post_send host=%s port=%s post_recv_len=%s",
                host,
                port,
                post_recv_len,
            )
