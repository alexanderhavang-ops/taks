from __future__ import annotations

import socket
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from martine.config import load_config


HOST = "127.0.0.1"
PORT = 8089

IDENTITY_DIR = "/opt/tak/tools/martine/runtime/identity"
CERT_PEM = f"{IDENTITY_DIR}/client.pem"
KEY_PEM = f"{IDENTITY_DIR}/client.key"
CA_PEM = f"{IDENTITY_DIR}/ca.pem"
CERT_METADATA = "/opt/tak/certs/cert-metadata.sh"
MARTINE_SECRETS_CONF = "/opt/tak/tools/takctl/secrets.d/martine.conf"
LEGACY_KEY_PASSWORD = "cert-pass-46-pass"

def _strip_quotes(v: str) -> str:
    s = str(v or "").strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s

def _read_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return out
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return out
    for raw in lines:
        line = str(raw or "").strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        k, v = line.split("=", 1)
        key = str(k or "").strip()
        val = _strip_quotes(v)
        if key:
            out[key] = val
    return out

def _cert_password_candidates() -> list[str | None]:
    vals: list[str | None] = [None]

    martine_kv = _read_simple_kv(Path(MARTINE_SECRETS_CONF))
    for key in ("martine_client_p12_pass", "martine_truststore_p12_pass"):
        v = str(martine_kv.get(key, "") or "").strip()
        if v:
            vals.append(v)

    try:
        for raw in Path(CERT_METADATA).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("PASS="):
                continue
            v = line.split("=", 1)[1].strip()
            v = _strip_quotes(v)
            if v:
                vals.append(v)
            break
    except Exception:
        pass

    vals.append(LEGACY_KEY_PASSWORD)

    out: list[str | None] = []
    seen = set()
    for v in vals:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out

def _load_client_chain(ctx: ssl.SSLContext) -> None:
    last = None
    for pw in _cert_password_candidates():
        try:
            if pw is None:
                ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM)
            else:
                ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM, password=pw)
            return
        except (ssl.SSLError, OSError, ValueError) as e:
            last = e
    if last is not None:
        raise last
    ctx.load_cert_chain(certfile=CERT_PEM, keyfile=KEY_PEM)


ALL_CHAT_ROOMS = "All Chat Rooms"


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_presence_xml(*, chat_uid: str, callsign: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=10))
    return (
        f'<event version="2.0" uid="{escape(chat_uid)}" type="a-f-G-U-C" how="h-e" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="32.076" ce="3.8" le="9999999.0"/>'
        f'<detail>'
        f'<contact callsign="{escape(callsign)}" endpoint="*:-1:stcp"/>'
        f'<__group name="Blue" role="Team Member"/>'
        f'<precisionlocation geopointsrc="GPS" altsrc="GPS"/>'
        f'<status battery="100"/>'
        f'<takv device="Martine" platform="ATAK-CIV" os="Linux" version="Martine/1.0"/>'
        f'<track speed="0.0" course="0.0"/>'
        f'<uid Droid="{escape(callsign)}"/>'
        f'</detail>'
        f'</event>'
    )


def build_atak_chat_xml(*, chat_uid: str, callsign: str, to: str, message: str) -> str:
    now_dt = datetime.now(timezone.utc)
    time_s = iso_z(now_dt)
    stale_s = iso_z(now_dt + timedelta(minutes=15))
    message_id = str(uuid.uuid4())
    uid = f"GeoChat.{chat_uid}.{to}.{message_id}"
    remarks_source = f"BAO.F.ATAK.{chat_uid}"
    return (
        f'<event version="2.0" uid="{escape(uid)}" type="b-t-f" how="h-g-i-g-o" '
        f'time="{time_s}" start="{time_s}" stale="{stale_s}">'
        f'<point lat="55.429800" lon="13.826700" hae="0.0" ce="9999999.0" le="9999999.0"/>'
        f'<detail>'
        f'<__chat parent="RootContactGroup" groupOwner="false" messageId="{escape(message_id)}" '
        f'chatroom="{escape(to)}" id="{escape(to)}" senderCallsign="{escape(callsign)}">'
        f'<chatgrp uid0="{escape(chat_uid)}" uid1="{escape(to)}" id="{escape(to)}"/>'
        f'</__chat>'
        f'<link uid="{escape(chat_uid)}" type="a-f-G-U-C" relation="p-p"/>'
        f'<__serverdestination destinations="127.0.0.1:4242:tcp:{escape(chat_uid)}"/>'
        f'<remarks source="{escape(remarks_source)}" to="{escape(to)}" time="{time_s}">{escape(message)}</remarks>'
        f'</detail>'
        f'</event>'
    )


def send_event(sock: ssl.SSLSocket, xml_text: str) -> None:
    sock.sendall(xml_text.encode("utf-8"))


def main() -> None:
    cfg = load_config()

    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=CA_PEM)
    _load_client_chain(ctx)

    print({"ok": True, "mode": "cot_tls_smoke", "host": HOST, "port": PORT}, flush=True)

    with socket.create_connection((HOST, PORT), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname="tak-hv-sandbox.se") as sock:
            print({"tls_version": sock.version(), "cipher": sock.cipher()}, flush=True)
            send_event(sock, build_presence_xml(chat_uid=cfg.chat_uid, callsign=cfg.callsign))
            time.sleep(0.2)
            send_event(
                sock,
                build_atak_chat_xml(
                    chat_uid=cfg.chat_uid,
                    callsign=cfg.callsign,
                    to=ALL_CHAT_ROOMS,
                    message="Martine TLS smoke via runtime identity.",
                ),
            )
            time.sleep(0.2)
            print({"ok": True, "sent": ["presence", "all-chat"]}, flush=True)


if __name__ == "__main__":
    main()
