# TAK Node Contract

This document defines the **contract** for a TAKS-managed node.

## Scope
A TAK node runs:
- TAK Server (Marti)
- takctl (CLI + web backend)
- nginx ingress managed by tak-installer

## Certificates
The node uses a **wildcard certificate** (e.g., `*.tak-hv-sandbox.se`).  
Certs are managed by the orchestrator, with offline nodes receiving encrypted certs.

## Network Ports – Canonical Model (DO NOT DEVIATE)

This section is **authoritative**. Any deviation is a bug.

### Public / Internet-facing ports

These are the **only ports users and browsers must ever access**.

| Port | Purpose | Notes |
|------|--------|-------|
| 443  | takctl UI + API | Not Marti, not WebTAK |
| 8446 | TAK Frontdoor (NGINX) | TLS termination + proxy |

All browser-based access to TAK **MUST** go via **:8446**.

---

### Internal / Local-only TAK Server ports

These ports are **never exposed directly**.

| Port | CoreConfig name | Purpose | Client cert |
|------|----------------|---------|-------------|
| 8089 | stdssl | ATAK CoT ingest | REQUIRED |
| 8090 | quic | QUIC transport | optional |
| 8443 | https | Legacy TAK HTTPS | REQUIRED (mTLS) |
| 8444 | fed_https | Federation | REQUIRED |
| 8447 | cert_https | Web / Admin / WebTAK | NOT required |

---

### Critical rules (non-negotiable)

1. **NGINX MUST NEVER proxy to port 8443**
   - 8443 requires client certificates
   - Browsers cannot use it
   - Causes TLS handshake failures and 502 errors

2. **NGINX MUST proxy to port 8447**
   - Designed for browser access
   - No client certificate required
   - Supports:
     - `/Marti`
     - `/webtak`
     - `/takproto` (WebSocket)
     - `/metrics`
     - `/clients`
     - `/admin`

3. **WebTAK CoT**
   - Public: `wss://<FQDN>:8446/takproto/`
   - NGINX → `https://127.0.0.1:8447/takproto/`

4. **X-Frame-Options**
   - TAK upstream sets `X-Frame-Options: DENY`
   - This breaks its own UI behind a proxy
   - NGINX on :8446 MUST override to:
     ```
     X-Frame-Options: SAMEORIGIN
     ```

---

### Reference Architecture


Internet
├─ 443 → takctl (FastAPI)
└─ 8446 → nginx (LE TLS)
└─ 8447 → TAK Server
├─ /Marti
├─ /webtak
├─ /takproto
└─ /metrics /clients /admin


If you are confused about ports, **read this section again**.

